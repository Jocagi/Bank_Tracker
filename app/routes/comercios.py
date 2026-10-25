import os
import re
import time
import threading
import uuid
import json
from json import JSONDecodeError
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlparse

from flask import current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for, Response
from . import bp
from .. import db
from ..models import Comercio, Regla, ReglaCondicion, Categoria, Subcategoria, Movimiento, Cuenta
from flask_login import current_user
from ..utils.classifier import reclasificar_comercio, snapshot_reglas_comercio, CAMPOS_VALIDOS, operadores_validos_para_campo, describir_regla
from ..utils.image_search import build_image_search_url, search_image_suggestions
from sqlalchemy.orm import joinedload, selectinload
from flask_login import login_required


ALLOWED_LOGO_TYPES = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp',
}

# Firmas binarias usadas para reconocer el formato real de una imagen cuando
# el servidor de origen omite el Content-Type o lo informa incorrectamente.
LOGO_MAGIC_SIGNATURES = (
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'GIF87a', 'image/gif'),
    (b'GIF89a', 'image/gif'),
)

# Dominio desde el que Brave sirve siempre sus miniaturas de imágenes; es el
# único host que el proxy de miniaturas tiene permitido reenviar.
BRAVE_IMAGE_PROXY_HOSTS = {'imgs.search.brave.com'}

# User-Agent "de navegador" usado para las descargas: reduce la probabilidad
# de que sitios de origen bloqueen peticiones con un User-Agent genérico.
BROWSER_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'
)

# El CDN de miniaturas de Brave (imgs.search.brave.com) aplica un límite de
# tasa agresivo y exige un Referer de su propio dominio para no rechazar la
# petición con 429.
BRAVE_PROXY_HEADERS = {
    'User-Agent': BROWSER_USER_AGENT,
    'Referer': 'https://search.brave.com/',
}

# Caché en memoria de miniaturas ya descargadas, para no volver a golpear el
# CDN de Brave (fácilmente saturable) en cada carga de la misma sugerencia.
_THUMBNAIL_CACHE = {}
_THUMBNAIL_CACHE_LOCK = threading.Lock()
THUMBNAIL_CACHE_TTL_SECONDS = 15 * 60
THUMBNAIL_CACHE_MAX_ENTRIES = 200


def format_sentence_case(text):
    """Convierte un texto a formato de oración (primera letra mayúscula, resto minúscula)"""
    if not text:
        return text
    # Limpiar caracteres especiales y espacios extra
    text = re.sub(r'[^\w\s]', '', text).strip()
    # Convertir a formato de oración
    return text.capitalize()


CONECTORES_VALIDOS = {'AND', 'OR'}


def _parse_reglas_payload(raw_json):
    """
    Parsea el JSON enviado por el formulario (campo oculto ``reglas_json``)
    y construye una lista de instancias ``Regla`` (con sus ``condiciones``)
    listas para asociarse a un comercio.

    El nombre (``descripcion``) de cada regla se deriva automáticamente de
    sus condiciones mediante ``describir_regla``: no se solicita ni se
    confía en texto libre del cliente, ya que no aporta información que no
    esté ya determinada por las condiciones mismas.

    Formato esperado::

        [
          {
            "tipo": "incluir",
            "condiciones": [
              {"conector": "AND", "negar": false, "campo": "descripcion",
               "operador": "contiene", "valor": "LA TORRE", "valor2": null},
              {"conector": "AND", "negar": true, "campo": "banco",
               "operador": "igual", "valor": "BI", "valor2": null}
            ]
          }
        ]

    Lanza ``ValueError`` con un mensaje apto para mostrar al usuario si el
    payload es inválido.
    """
    if not raw_json or not raw_json.strip():
        return []

    try:
        data = json.loads(raw_json)
    except JSONDecodeError:
        raise ValueError('El formato de las reglas de clasificación es inválido.')

    if not isinstance(data, list):
        raise ValueError('El formato de las reglas de clasificación es inválido.')

    reglas = []
    for regla_data in data:
        if not isinstance(regla_data, dict):
            raise ValueError('El formato de las reglas de clasificación es inválido.')

        tipo = (regla_data.get('tipo') or '').strip().lower()
        condiciones_data = regla_data.get('condiciones') or []

        if tipo not in ('incluir', 'excluir') or not condiciones_data:
            # Reglas incompletas (sin tipo o condiciones) se ignoran
            continue

        regla = Regla(tipo=tipo)
        for indice, cond_data in enumerate(condiciones_data):
            if not isinstance(cond_data, dict):
                continue
            campo = (cond_data.get('campo') or '').strip()
            operador = (cond_data.get('operador') or '').strip()
            valor = cond_data.get('valor')
            valor2 = cond_data.get('valor2')
            conector = (cond_data.get('conector') or 'AND').strip().upper()
            negar = bool(cond_data.get('negar'))

            if campo not in CAMPOS_VALIDOS:
                raise ValueError(f'Campo de condición inválido: "{campo}".')
            if operador not in operadores_validos_para_campo(campo):
                raise ValueError(f'Operador inválido ("{operador}") para el campo "{campo}".')
            if conector not in CONECTORES_VALIDOS:
                conector = 'AND'
            valor = (valor or '').strip() if isinstance(valor, str) else valor
            valor2 = (valor2 or '').strip() if isinstance(valor2, str) else valor2
            if not valor:
                # Una condición sin valor no puede evaluarse; se descarta.
                continue

            regla.condiciones.append(ReglaCondicion(
                orden=indice,
                conector=conector,
                negar=negar,
                campo=campo,
                operador=operador,
                valor=valor,
                valor2=valor2 or None,
            ))

        if not regla.condiciones:
            continue

        # El nombre de la regla se calcula siempre a partir de sus
        # condiciones, para que quede consistente aunque cambien después.
        regla.descripcion = describir_regla(regla)[:200]
        reglas.append(regla)

    return reglas


def _serializar_reglas(comercio):
    """Convierte las reglas de un comercio a una estructura JSON-friendly
    para inicializar el constructor de reglas en el formulario de edición."""
    reglas = []
    for regla in sorted(comercio.reglas, key=lambda r: r.id):
        reglas.append({
            'descripcion': regla.descripcion,
            'tipo': regla.tipo,
            'condiciones': [
                {
                    'conector': cond.conector,
                    'negar': cond.negar,
                    'campo': cond.campo,
                    'operador': cond.operador,
                    'valor': cond.valor,
                    'valor2': cond.valor2,
                }
                for cond in sorted(regla.condiciones, key=lambda c: c.orden)
            ]
        })
    return reglas


def _obtener_catalogos_reglas():
    """
    Recupera los catálogos (bancos, tipos de cuenta, cuentas y monedas)
    usados para construir listas desplegables en el constructor de reglas,
    en lugar de obligar a escribir el valor a mano.

    Igual que en el resto de pantallas, solo se ofrecen las cuentas (y los
    valores derivados de ellas) que pertenecen al usuario autenticado.
    """
    cuentas_usuario = (
        Cuenta.query
        .filter(Cuenta.user_id == current_user.id)
        .order_by(Cuenta.banco, Cuenta.tipo_cuenta)
        .all()
    )

    bancos = sorted({(c.banco or '').strip() for c in cuentas_usuario if (c.banco or '').strip()})
    tipos_cuenta = sorted({(c.tipo_cuenta or '').strip() for c in cuentas_usuario if (c.tipo_cuenta or '').strip()})
    monedas_cuentas = {(c.moneda or '').strip().upper() for c in cuentas_usuario if (c.moneda or '').strip()}
    monedas_movimientos = {
        (valor or '').strip().upper()
        for (valor,) in db.session.query(Movimiento.moneda)
        .filter(Movimiento.user_id == current_user.id)
        .distinct()
        if (valor or '').strip()
    }
    monedas = sorted(monedas_cuentas | monedas_movimientos)

    cuentas = []
    for cuenta in cuentas_usuario:
        valor = (cuenta.alias or cuenta.numero_cuenta or '').strip()
        if not valor:
            continue
        detalle = ' - '.join(filter(None, [cuenta.banco, cuenta.tipo_cuenta, cuenta.numero_cuenta]))
        cuentas.append({'value': valor, 'label': f'{valor} ({detalle})' if detalle else valor})

    return {
        'banco': bancos,
        'tipo_cuenta': tipos_cuenta,
        'moneda': monedas,
        'cuenta': cuentas,
    }


def _logo_folder(entity_type='comercios'):
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], entity_type)
    os.makedirs(folder, exist_ok=True)
    return folder


def _sniff_image_content_type(content):
    """Detecta el tipo real de una imagen a partir de su firma binaria."""
    for signature, content_type in LOGO_MAGIC_SIGNATURES:
        if content.startswith(signature):
            return content_type
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'image/webp'
    return None


def _extension_for_content(content_type, content):
    """Resuelve la extensión permitida, confiando primero en el Content-Type
    informado y, si no es válido, en la firma binaria real de los bytes
    (algunos sitios de origen omiten el header o lo informan mal)."""
    extension = ALLOWED_LOGO_TYPES.get((content_type or '').lower())
    if extension:
        return extension
    sniffed_type = _sniff_image_content_type(content)
    return ALLOWED_LOGO_TYPES.get(sniffed_type)


def _download_image(image_url, extra_headers=None, retry_on_rate_limit=False):
    if not image_url.startswith(('http://', 'https://')):
        raise ValueError('La URL de la imagen no es válida.')
    max_bytes = current_app.config.get('MAX_LOGO_BYTES', 5 * 1024 * 1024)
    headers = {'User-Agent': BROWSER_USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)

    attempts = 2 if retry_on_rate_limit else 1
    for attempt in range(attempts):
        try:
            req = Request(image_url.replace(' ', '%20'), headers=headers)
            with urlopen(req, timeout=10) as response:
                content_type = response.headers.get_content_type().lower()
                content = response.read(max_bytes + 1)
            break
        except HTTPError as error:
            # El CDN de miniaturas de Brave aplica un límite de tasa que se
            # libera en pocos segundos; un único reintento corto suele bastar.
            if error.code == 429 and attempt < attempts - 1:
                time.sleep(1.5)
                continue
            raise

    if len(content) > max_bytes:
        raise ValueError('El logo debe tener un tamaño máximo de 5 MB.')
    if not _extension_for_content(content_type, content):
        raise ValueError('El logo debe ser una imagen JPG, PNG, GIF o WEBP.')
    return content_type, content


def _download_image_auto(image_url):
    """Descarga una imagen aplicando las cabeceras y reintentos adecuados
    según el host (el CDN de miniaturas de Brave necesita trato especial)."""
    if urlparse(image_url).hostname in BRAVE_IMAGE_PROXY_HOSTS:
        return _download_image(image_url, extra_headers=BRAVE_PROXY_HEADERS, retry_on_rate_limit=True)
    return _download_image(image_url)


def _save_logo(file_storage=None, image_url=None, entity_type='comercios', fallback_image_url=None):
    content_type = None
    content = None
    if not (file_storage and file_storage.filename) and not image_url:
        return None

    if file_storage and file_storage.filename:
        content_type = (file_storage.mimetype or '').lower().split(';')[0]
        content = file_storage.read(current_app.config.get('MAX_LOGO_BYTES', 5 * 1024 * 1024) + 1)
    elif image_url:
        # Al elegir una sugerencia se intenta primero la imagen original y,
        # si falla (host caído, formato no soportado, bloqueo, etc.), se
        # reintenta con la miniatura de Brave, que siempre es una imagen
        # válida servida de forma confiable.
        candidate_urls = [image_url]
        if fallback_image_url and fallback_image_url != image_url:
            candidate_urls.append(fallback_image_url)
        for index, candidate_url in enumerate(candidate_urls):
            try:
                content_type, content = _download_image_auto(candidate_url)
                break
            except Exception:
                if index == len(candidate_urls) - 1:
                    raise

    if not content or len(content) > current_app.config.get('MAX_LOGO_BYTES', 5 * 1024 * 1024):
        raise ValueError('El logo debe tener un tamaño máximo de 5 MB.')
    extension = _extension_for_content(content_type, content)
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
    if not filename.startswith(('comercios/', 'categorias/', 'subcategorias/', 'paises/')):
        return ('', 404)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@bp.route('/comercios/logo-image-proxy')
@login_required
def logo_image_proxy():
    """Reenvía las miniaturas de Brave desde el servidor en lugar de que el
    navegador las cargue directamente, evitando fallos intermitentes por
    bloqueos de hotlinking/límites de tasa del CDN externo. Cachea en
    memoria las miniaturas ya descargadas para no volver a solicitarlas."""
    image_url = request.args.get('url', '')
    if not image_url.startswith(('http://', 'https://')):
        return ('', 400)
    if urlparse(image_url).hostname not in BRAVE_IMAGE_PROXY_HOSTS:
        return ('', 400)

    now = time.monotonic()
    with _THUMBNAIL_CACHE_LOCK:
        cached = _THUMBNAIL_CACHE.get(image_url)
        if cached and cached[0] > now:
            _, content_type, content = cached
            return Response(content, mimetype=content_type, headers={'Cache-Control': 'public, max-age=86400'})

    try:
        content_type, content = _download_image(image_url, extra_headers=BRAVE_PROXY_HEADERS, retry_on_rate_limit=True)
    except Exception:
        return ('', 502)

    with _THUMBNAIL_CACHE_LOCK:
        if len(_THUMBNAIL_CACHE) >= THUMBNAIL_CACHE_MAX_ENTRIES:
            oldest_key = min(_THUMBNAIL_CACHE, key=lambda key: _THUMBNAIL_CACHE[key][0])
            _THUMBNAIL_CACHE.pop(oldest_key, None)
        _THUMBNAIL_CACHE[image_url] = (now + THUMBNAIL_CACHE_TTL_SECONDS, content_type, content)

    return Response(content, mimetype=content_type, headers={'Cache-Control': 'public, max-age=86400'})


@bp.route('/comercios/logo-suggestions')
@login_required
def logo_suggestions():
    nombre = request.args.get('nombre', '').strip()
    if not nombre:
        return jsonify({'suggestions': []})

    termino = request.args.get('termino', 'logo')
    search_url = build_image_search_url(nombre, termino)
    try:
        result = search_image_suggestions(nombre, termino)
        return jsonify(result)
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
    except (TimeoutError, OSError, JSONDecodeError):
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
        # Buscar dentro de las reglas (descripción, tipo o cualquier valor de condición)
        query = query.join(Regla).outerjoin(ReglaCondicion).filter(
            (Regla.descripcion.ilike(f"%{regla_q}%")) |
            (Regla.tipo.ilike(f"%{regla_q}%")) |
            (ReglaCondicion.valor.ilike(f"%{regla_q}%")) |
            (ReglaCondicion.valor2.ilike(f"%{regla_q}%"))
        ).distinct()

    # Eager-load reglas y categoria para evitar N+1 y paginar en DB
    pagination = query.order_by(Comercio.nombre.asc()).options(
        selectinload(Comercio.reglas).selectinload(Regla.condiciones),
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
    regla_prellenada = None
    if pre_regla:
        regla_prellenada = {
            'descripcion': pre_nombre or 'Regla automática',
            'tipo': 'incluir',
            'condiciones': [{'campo': 'descripcion', 'operador': 'comodin', 'valor': pre_regla}]
        }
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form.get('descripcion') or None
        categoria_id = int(request.form['categoria_id'])
        subcategoria_id_raw = request.form.get('subcategoria_id') or ''
        subcategoria_id = int(subcategoria_id_raw) if subcategoria_id_raw else None
        tipo_contabilizacion  = request.form['tipo_contabilizacion']
        reglas_json = request.form.get('reglas_json', '')

        try:
            nuevas_reglas = _parse_reglas_payload(reglas_json)
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla, regla_prellenada=regla_prellenada, catalogos=_obtener_catalogos_reglas())

        logo_filename = None
        try:
            logo_filename = _save_logo(
                request.files.get('logo'),
                request.form.get('logo_url') or None,
                fallback_image_url=request.form.get('logo_thumbnail_url') or None
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla, regla_prellenada=regla_prellenada, catalogos=_obtener_catalogos_reglas())
        except Exception:
            flash('No fue posible descargar el logo seleccionado.', 'danger')
            return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla, regla_prellenada=regla_prellenada, catalogos=_obtener_catalogos_reglas())

        if subcategoria_id is not None:
            subcategoria = Subcategoria.query.get_or_404(subcategoria_id)
            if subcategoria.categoria_id != categoria_id:
                _delete_logo(logo_filename)
                flash('La subcategoría debe pertenecer a la categoría seleccionada.', 'danger')
                return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla, regla_prellenada=regla_prellenada, catalogos=_obtener_catalogos_reglas())

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

        # Asociar las reglas de clasificación (con sus condiciones) al comercio
        for regla in nuevas_reglas:
            regla.comercio_id = nuevo_comercio.id
            db.session.add(regla)
        db.session.commit()

        # Solo se reevalúan los movimientos que coinciden con las reglas del
        # nuevo comercio (los demás no pueden verse afectados).
        cambios = reclasificar_comercio(nuevo_comercio.id)

        flash(f'Comercio y reglas agregados correctamente. Movimientos reclasificados: {cambios}.', 'success')
        return redirect(url_for('main.list_comercios'))
    return render_template('comercios_add.html', categorias=categorias, subcategorias=subcategorias, pre_nombre=pre_nombre, pre_regla=pre_regla, regla_prellenada=regla_prellenada, catalogos=_obtener_catalogos_reglas())


@bp.route('/comercios/<int:comercio_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    subcategorias = Subcategoria.query.options(joinedload(Subcategoria.categoria)).order_by(Subcategoria.nombre).all()
    if request.method == 'POST':
        reglas_json = request.form.get('reglas_json', '')
        try:
            nuevas_reglas = _parse_reglas_payload(reglas_json)
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias, reglas_data=_serializar_reglas(comercio), catalogos=_obtener_catalogos_reglas())

        previous_logo = comercio.logo_filename
        new_logo = None
        try:
            new_logo = _save_logo(
                request.files.get('logo'),
                request.form.get('logo_url') or None,
                fallback_image_url=request.form.get('logo_thumbnail_url') or None
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias, reglas_data=_serializar_reglas(comercio), catalogos=_obtener_catalogos_reglas())
        except Exception:
            flash('No fue posible descargar el logo seleccionado.', 'danger')
            return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias, reglas_data=_serializar_reglas(comercio), catalogos=_obtener_catalogos_reglas())

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
                return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias, reglas_data=_serializar_reglas(comercio), catalogos=_obtener_catalogos_reglas())
        comercio.subcategoria_id = subcategoria_id
        comercio.tipo_contabilizacion = request.form['tipo_contabilizacion']
        if new_logo:
            comercio.logo_filename = new_logo
        elif request.form.get('remove_logo') == '1':
            comercio.logo_filename = None
        
        # Copia de las reglas actuales antes de reemplazarlas: los movimientos
        # que coincidían con ellas también deben reevaluarse.
        reglas_previas = snapshot_reglas_comercio(comercio.id)

        # Eliminar reglas antiguas y sus condiciones (el delete masivo no
        # dispara el cascade ORM, así que se eliminan explícitamente)
        regla_ids_antiguas = [rid for (rid,) in db.session.query(Regla.id).filter_by(comercio_id=comercio.id).all()]
        if regla_ids_antiguas:
            ReglaCondicion.query.filter(ReglaCondicion.regla_id.in_(regla_ids_antiguas)).delete(synchronize_session=False)
        Regla.query.filter_by(comercio_id=comercio.id).delete(synchronize_session=False)

        # Agregar reglas nuevas
        for regla in nuevas_reglas:
            regla.comercio_id = comercio.id
            db.session.add(regla)
        db.session.commit()
        if previous_logo and comercio.logo_filename != previous_logo:
            _delete_logo(previous_logo)
        
        # Reevaluar solo los movimientos del comercio y los que coinciden con
        # sus reglas anteriores o nuevas.
        cambios = reclasificar_comercio(comercio.id, reglas_previas)

        flash(f'Comercio actualizado. Movimientos reclasificados: {cambios}.', 'success')
        return redirect(url_for('main.list_comercios'))
    return render_template('comercios_edit.html', comercio=comercio, categorias=categorias, subcategorias=subcategorias, reglas_data=_serializar_reglas(comercio), catalogos=_obtener_catalogos_reglas())


@bp.route('/comercios/<int:comercio_id>/delete', methods=['POST'])
@login_required
def delete_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    logo_filename = comercio.logo_filename
    reglas_previas = snapshot_reglas_comercio(comercio.id)
    db.session.delete(comercio)
    db.session.commit()
    _delete_logo(logo_filename)
    reclasificar_comercio(comercio_id, reglas_previas)
    flash('Comercio eliminado', 'warning')
    return redirect(url_for('main.list_comercios'))
