import os
import re
import uuid
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json

from flask import current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from . import bp
from .. import db
from ..models import Comercio, Regla, Categoria, Subcategoria, Movimiento
from flask_login import current_user
from ..utils.classifier import reclasificar_movimientos
from sqlalchemy.orm import joinedload
from flask_login import login_required


ALLOWED_LOGO_TYPES = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp',
}

BRAVE_IMAGE_COUNTRIES = {
    'AR', 'AU', 'AT', 'BE', 'BR', 'CA', 'CL', 'DK', 'FI', 'FR', 'DE',
    'GR', 'HK', 'IN', 'ID', 'IT', 'JP', 'KR', 'MY', 'MX', 'NL', 'NZ',
    'NO', 'CN', 'PL', 'PT', 'PH', 'RU', 'SA', 'ZA', 'ES', 'SE', 'CH',
    'TW', 'TR', 'GB', 'US', 'ALL',
}


def format_sentence_case(text):
    """Convierte un texto a formato de oración (primera letra mayúscula, resto minúscula)"""
    if not text:
        return text
    # Limpiar caracteres especiales y espacios extra
    text = re.sub(r'[^\w\s]', '', text).strip()
    # Convertir a formato de oración
    return text.capitalize()


def _logo_folder(entity_type='comercios'):
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], entity_type)
    os.makedirs(folder, exist_ok=True)
    return folder


def _save_logo(file_storage=None, image_url=None, entity_type='comercios'):
    content_type = None
    content = None
    if file_storage and file_storage.filename:
        content_type = (file_storage.mimetype or '').lower().split(';')[0]
        content = file_storage.read(current_app.config.get('MAX_LOGO_BYTES', 5 * 1024 * 1024) + 1)
    elif image_url:
        if not image_url.startswith(('http://', 'https://')):
            raise ValueError('La URL de la imagen no es válida.')
        image_url = image_url.replace(' ', '%20')
        req = Request(image_url, headers={'User-Agent': 'BankTracker/1.0'})
        with urlopen(req, timeout=10) as response:
            content_type = response.headers.get_content_type().lower()
            content = response.read(current_app.config.get('MAX_LOGO_BYTES', 5 * 1024 * 1024) + 1)

    if not content or len(content) > current_app.config.get('MAX_LOGO_BYTES', 5 * 1024 * 1024):
        raise ValueError('El logo debe tener un tamaño máximo de 5 MB.')
    extension = ALLOWED_LOGO_TYPES.get(content_type)
    if not extension:
        raise ValueError('El logo debe ser una imagen JPG, PNG, GIF o WEBP.')

    filename = f'{uuid.uuid4().hex}.{extension}'
    relative_filename = os.path.join(entity_type, filename).replace(os.sep, '/')
    with open(os.path.join(_logo_folder(entity_type), filename), 'wb') as logo_file:
        logo_file.write(content)
    return relative_filename


def _delete_logo(filename):
    if not filename:
        return
    path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    if os.path.isfile(path):
        os.remove(path)


@bp.route('/comercios/logo/<path:filename>')
@login_required
def comercio_logo(filename):
    if not filename.startswith(('comercios/', 'categorias/', 'subcategorias/')):
        return ('', 404)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


def _search_brave_images(query):
    api_key = current_app.config.get('BRAVE_SEARCH_API_KEY', '')
    if not api_key:
        raise RuntimeError('BRAVE_SEARCH_API_KEY no está configurada.')

    country = current_app.config.get('BRAVE_SEARCH_COUNTRY', 'ALL')
    if country not in BRAVE_IMAGE_COUNTRIES:
        country = 'ALL'

    api_url = 'https://api.search.brave.com/res/v1/images/search?' + urlencode({
        'q': query,
        'count': 3,
        'safesearch': 'strict',
        'country': country,
        'search_lang': current_app.config.get('BRAVE_SEARCH_LANG', 'es')
    })
    req = Request(api_url, headers={
        'Accept': 'application/json',
        'X-Subscription-Token': api_key,
        'User-Agent': 'BankTracker/1.0 (logo suggestions)'
    })
    payload = json.loads(urlopen(req, timeout=10).read().decode('utf-8'))
    if payload.get('error'):
        raise RuntimeError(payload['error'])

    return [
        {
            'url': item.get('properties', {}).get('url') or item.get('url'),
            'thumbnail_url': item.get('thumbnail', {}).get('src'),
            'title': item.get('title') or 'Logo sugerido'
        }
        for item in payload.get('results', [])
        if (item.get('properties', {}).get('url') or item.get('url', '')).startswith(('http://', 'https://'))
        and item.get('thumbnail', {}).get('src', '').startswith(('http://', 'https://'))
    ][:3]


@bp.route('/comercios/logo-suggestions')
@login_required
def logo_suggestions():
    nombre = request.args.get('nombre', '').strip()
    if not nombre:
        return jsonify({'suggestions': []})

    query = f'{nombre} logo'
    search_url = 'https://www.google.com/search?' + urlencode({
        'tbm': 'isch',
        'q': query,
        'gl': current_app.config.get('BRAVE_SEARCH_COUNTRY', 'GT').lower(),
        'hl': current_app.config.get('BRAVE_SEARCH_LANG', 'es')
    })

    try:
        suggestions = _search_brave_images(query)
        return jsonify({'suggestions': suggestions, 'search_url': search_url})
    except RuntimeError as error:
        return jsonify({
            'suggestions': [],
            'search_url': search_url,
            'message': str(error)
        })
    except HTTPError as error:
        if error.code == 429:
            message = 'El servicio de imágenes alcanzó temporalmente su límite de consultas. Inténtalo de nuevo en unos segundos.'
        else:
            message = f'No fue posible completar la búsqueda de logos (HTTP {error.code}).'

        return jsonify({
            'suggestions': [],
            'search_url': search_url,
            'message': message
        })
    except (TimeoutError, OSError, json.JSONDecodeError):
        return jsonify({
            'suggestions': [],
            'search_url': search_url,
            'message': 'No fue posible conectar con los servicios de imágenes. Verifica tu conexión e inténtalo de nuevo.'
        })


@bp.route('/comercios')
@login_required
def list_comercios():
    # Obtener todos los comercios y sus reglas
    # Filtros desde query string
    nombre_q = request.args.get('q_name', '').strip()
    categoria_id = request.args.get('categoria_id', type=int)
    subcategoria_id_raw = request.args.get('subcategoria_id', '').strip()
    subcategoria_id = None
    if subcategoria_id_raw != '':
        try:
            subcategoria_id = int(subcategoria_id_raw)
        except ValueError:
            subcategoria_id = None
    tipo = request.args.get('tipo', '').strip()
    regla_q = request.args.get('regla', '').strip()
    owner_id = request.args.get('owner_id', type=int)
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=50, type=int)
    if per_page not in (25, 50, 100):
        per_page = 50

    # Construir consulta dinámica
    query = Comercio.query
    if categoria_id:
        query = query.filter(Comercio.categoria_id == categoria_id)
    if subcategoria_id is not None:
        if subcategoria_id == 0:
            query = query.filter(Comercio.subcategoria_id.is_(None))
        else:
            query = query.filter(Comercio.subcategoria_id == subcategoria_id)
    if tipo:
        query = query.filter(Comercio.tipo_contabilizacion == tipo)
    if nombre_q:
            query = query.filter(
                (Comercio.nombre.ilike(f"%{nombre_q}%")) |
                (Comercio.descripcion.ilike(f"%{nombre_q}%"))
            )
    if regla_q:
        # Buscar dentro de las reglas (descripcion, criterio o tipo)
        query = query.join(Regla).filter(
            (Regla.descripcion.ilike(f"%{regla_q}%")) |
            (Regla.criterio.ilike(f"%{regla_q}%")) |
            (Regla.tipo.ilike(f"%{regla_q}%"))
        ).distinct()

    # Eager-load reglas y categoria para evitar N+1 y paginar en DB
    pagination = query.order_by(Comercio.nombre.asc()).options(
        joinedload(Comercio.reglas),
        joinedload(Comercio.categoria),
        joinedload(Comercio.subcategoria)
    ).paginate(page=page, per_page=per_page, error_out=False)
    comercios = pagination.items
    total_comercios = pagination.total
    range_start = 0 if total_comercios == 0 else ((pagination.page - 1) * pagination.per_page) + 1
    range_end = min(pagination.page * pagination.per_page, total_comercios)

    # Precalcular counts para evitar N+1
    # Conteo de movimientos: si admin puede filtrar por owner_id, sino solo del usuario actual
    comercio_ids = [c.id for c in comercios]
    movimiento_counts = {}
    if comercio_ids:
        movimiento_query = db.session.query(Movimiento.comercio_id, db.func.count(Movimiento.id)).filter(
            Movimiento.comercio_id.in_(comercio_ids)
        )
        if hasattr(current_user, 'is_admin') and current_user.is_admin() and owner_id:
            movimiento_query = movimiento_query.filter(Movimiento.user_id == owner_id)
        else:
            movimiento_query = movimiento_query.filter(Movimiento.user_id == current_user.id)
        movimiento_counts = {row[0]: row[1] for row in movimiento_query.group_by(Movimiento.comercio_id).all()}
    for c in comercios:
        c.movimientos_count = movimiento_counts.get(c.id, 0)

    # Pasar listas auxiliares (categorias) y valores de filtro actuales para la plantilla
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    subcategorias_query = Subcategoria.query.options(joinedload(Subcategoria.categoria)).order_by(Subcategoria.nombre)
    if categoria_id:
        subcategorias_query = subcategorias_query.filter(Subcategoria.categoria_id == categoria_id)
    subcategorias = subcategorias_query.all()
    filters = {
        'q_name': nombre_q,
        'categoria_id': categoria_id or '',
        'subcategoria_id': subcategoria_id_raw,
        'tipo': tipo,
        'regla': regla_q,
        'owner_id': owner_id or '',
        'per_page': per_page
    }
    return render_template(
        'comercios.html',
        comercios=comercios,
        categorias=categorias,
        subcategorias=subcategorias,
        filters=filters,
        pagination=pagination,
        total_comercios=total_comercios,
        range_start=range_start,
        range_end=range_end
    )


@bp.route('/comercios/add', methods=['GET', 'POST'])
@login_required
def add_comercio():
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    subcategorias = Subcategoria.query.options(joinedload(Subcategoria.categoria)).order_by(Subcategoria.nombre).all()
    
    # Obtener datos pre-llenados de la URL
    pre_nombre = format_sentence_case(request.args.get('nombre', ''))
    pre_regla = request.args.get('regla', '')
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form.get('descripcion') or None
        categoria_id = int(request.form['categoria_id'])
        subcategoria_id_raw = request.form.get('subcategoria_id') or ''
        subcategoria_id = int(subcategoria_id_raw) if subcategoria_id_raw else None
        tipo_contabilizacion  = request.form['tipo_contabilizacion']
        logo_filename = None
        try:
            logo_filename = _save_logo(
                request.files.get('logo'),
                request.form.get('logo_url') or None
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla)
        except Exception:
            flash('No fue posible descargar el logo seleccionado.', 'danger')
            return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla)

        if subcategoria_id is not None:
            subcategoria = Subcategoria.query.get_or_404(subcategoria_id)
            if subcategoria.categoria_id != categoria_id:
                _delete_logo(logo_filename)
                flash('La subcategoría debe pertenecer a la categoría seleccionada.', 'danger')
                return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla)

        # Crear nuevo comercio
        nuevo_comercio = Comercio(
            nombre=nombre,
            descripcion=descripcion,
            categoria_id=categoria_id,
            subcategoria_id=subcategoria_id,
            tipo_contabilizacion=tipo_contabilizacion,
            logo_filename=logo_filename
        )
        db.session.add(nuevo_comercio)
        db.session.flush()  # Para obtener nuevo_comercio.id

        # Procesar reglas de clasificación
        descripciones = request.form.getlist('reg_descripcion')
        tipos = request.form.getlist('reg_tipo')
        criterios = request.form.getlist('reg_criterio')
        for desc, tp, crit in zip(descripciones, tipos, criterios):
            desc = desc.strip()
            crit = crit.strip()
            if desc and crit:
                regla = Regla(
                    comercio_id=nuevo_comercio.id,
                    descripcion=desc,
                    tipo=tp,
                    criterio=crit
                )
                db.session.add(regla)
        db.session.commit()

        # Clasificar movimientos automáticamente
        reclasificar_movimientos()

        flash('Comercio y reglas agregados correctamente.', 'success')
        return redirect(url_for('main.list_comercios'))
    return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla)


@bp.route('/comercios/<int:comercio_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    subcategorias = Subcategoria.query.options(joinedload(Subcategoria.categoria)).order_by(Subcategoria.nombre).all()
    if request.method == 'POST':
        previous_logo = comercio.logo_filename
        new_logo = None
        try:
            new_logo = _save_logo(
                request.files.get('logo'),
                request.form.get('logo_url') or None
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias)
        except Exception:
            flash('No fue posible descargar el logo seleccionado.', 'danger')
            return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias)

        comercio.nombre = request.form['nombre']
        comercio.descripcion = request.form.get('descripcion') or None
        comercio.categoria_id = int(request.form['categoria_id'])
        subcategoria_id_raw = request.form.get('subcategoria_id') or ''
        subcategoria_id = int(subcategoria_id_raw) if subcategoria_id_raw else None
        if subcategoria_id is not None:
            subcategoria = Subcategoria.query.get_or_404(subcategoria_id)
            if subcategoria.categoria_id != comercio.categoria_id:
                _delete_logo(new_logo)
                flash('La subcategoría debe pertenecer a la categoría seleccionada.', 'danger')
                return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias)
        comercio.subcategoria_id = subcategoria_id
        comercio.tipo_contabilizacion = request.form['tipo_contabilizacion']
        if new_logo:
            comercio.logo_filename = new_logo
        elif request.form.get('remove_logo') == '1':
            comercio.logo_filename = None
        
        # Eliminar reglas antiguas
        Regla.query.filter_by(comercio_id=comercio.id).delete()
        
        # Agregar reglas nuevas
        for desc, tp, crit in zip(
            request.form.getlist('reg_descripcion'),
            request.form.getlist('reg_tipo'),
            request.form.getlist('reg_criterio')
        ):
            if desc.strip() and crit.strip():
                db.session.add(Regla(
                    comercio_id=comercio.id,
                    descripcion=desc.strip(),
                    tipo=tp,
                    criterio=crit.strip()
                ))
        db.session.commit()
        if previous_logo and comercio.logo_filename != previous_logo:
            _delete_logo(previous_logo)
        
        # Re-clasificar todos los movimientos tras modificar reglas
        reclasificar_movimientos()

        flash('Comercio actualizado', 'success')
        return redirect(url_for('main.list_comercios'))
    return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias)


@bp.route('/comercios/<int:comercio_id>/delete', methods=['POST'])
@login_required
def delete_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    logo_filename = comercio.logo_filename
    db.session.delete(comercio)
    db.session.commit()
    _delete_logo(logo_filename)
    reclasificar_movimientos()
    flash('Comercio eliminado', 'warning')
    return redirect(url_for('main.list_comercios'))
