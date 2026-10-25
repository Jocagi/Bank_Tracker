from flask import render_template, request, flash, redirect, url_for, Response, abort, current_app
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from .. import db
from ..models import Comercio, Categoria, Subcategoria, TipoCambio, Regla, ReglaCondicion
from ..utils.classifier import describir_regla
from . import bp
from flask_login import login_required, current_user
import json

from ..utils.database_backup import backup_database


def _condiciones_desde_regla_import(r):
    """
    Normaliza las condiciones de una regla importada. Soporta el formato
    nuevo (``condiciones``: lista de condiciones) y, por compatibilidad,
    el formato antiguo basado en un único ``criterio`` de texto sobre la
    descripción (comodín '*' o '=' para coincidencia exacta).
    """
    condiciones_data = r.get('condiciones')
    if condiciones_data:
        resultado = []
        for idx, c in enumerate(condiciones_data):
            campo = (c.get('campo') or '').strip()
            operador = (c.get('operador') or '').strip()
            valor = c.get('valor')
            if not campo or not operador or not valor:
                continue
            resultado.append({
                'orden': c.get('orden', idx),
                'conector': (c.get('conector') or 'AND').strip().upper() or 'AND',
                'negar': bool(c.get('negar')),
                'campo': campo,
                'operador': operador,
                'valor': valor,
                'valor2': c.get('valor2'),
            })
        return resultado

    # Formato antiguo: un único criterio de texto sobre la descripción
    criterio = (r.get('criterio') or '').strip()
    if not criterio:
        return []
    if criterio.startswith('='):
        operador, valor = 'igual', criterio[1:].strip()
    else:
        operador, valor = 'comodin', criterio
    if not valor:
        return []
    return [{
        'orden': 0, 'conector': 'AND', 'negar': False,
        'campo': 'descripcion', 'operador': operador, 'valor': valor, 'valor2': None,
    }]


def _firma_condiciones(condiciones):
    return tuple(sorted(
        (c['campo'], c['operador'], c['valor'], c.get('valor2'), c['conector'], c['negar'])
        for c in condiciones
    ))


@bp.route('/export_config')
@login_required
def export_config():
    # Only admin users can export the full configuration
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        abort(403)

    # Tipos de cambio
    tipos = []
    for t in TipoCambio.query.order_by(TipoCambio.moneda).all():
        tipos.append({
            'id': t.id,
            'moneda': t.moneda,
            'valor': t.valor,
            'updated_at': t.updated_at.isoformat() if t.updated_at else None
        })

    # Categorías
    categorias = []
    for c in Categoria.query.order_by(Categoria.nombre).all():
        categorias.append({
            'id': c.id,
            'nombre': c.nombre
        })

    # Subcategorías
    subcategorias = []
    for s in Subcategoria.query.join(Categoria).order_by(Categoria.nombre, Subcategoria.nombre).all():
        subcategorias.append({
            'id': s.id,
            'nombre': s.nombre,
            'categoria_id': s.categoria_id,
            'categoria_nombre': s.categoria.nombre if s.categoria else None
        })

    # Comercios + reglas
    comercios = []
    for cm in Comercio.query.order_by(Comercio.nombre).all():
        reglas = []
        for r in cm.reglas:
            reglas.append({
                'id': r.id,
                'descripcion': r.descripcion,
                'tipo': r.tipo,
                'condiciones': [
                    {
                        'orden': c.orden,
                        'conector': c.conector,
                        'negar': c.negar,
                        'campo': c.campo,
                        'operador': c.operador,
                        'valor': c.valor,
                        'valor2': c.valor2,
                    }
                    for c in sorted(r.condiciones, key=lambda c: c.orden)
                ]
            })
        comercios.append({
            'id': cm.id,
            'nombre': cm.nombre,
            'categoria_id': cm.categoria_id,
            'categoria_nombre': cm.categoria.nombre if cm.categoria else None,
            'subcategoria_id': cm.subcategoria_id,
            'subcategoria_nombre': cm.subcategoria.nombre if cm.subcategoria else None,
            'tipo_contabilizacion': cm.tipo_contabilizacion,
            'reglas': reglas
        })

    payload = {
        'tipos_cambio': tipos,
        'categorias': categorias,
        'subcategorias': subcategorias,
        'comercios': comercios
    }

    body = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"bank_tracker_config_{__import__('datetime').date.today().isoformat()}.json"
    resp = Response(body, mimetype='application/json; charset=utf-8')
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp



@bp.route('/import_config', methods=['POST'])
@login_required
def import_config():
    # Only admin users can import the full configuration
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        abort(403)

    uploaded = request.files.get('file')
    if not uploaded:
        flash('No se subió ningún archivo.', 'warning')
        return redirect(url_for('main.dashboard'))

    try:
        data = json.load(uploaded)
    except Exception as e:
        flash(f'Archivo JSON inválido: {e}', 'danger')
        return redirect(url_for('main.dashboard'))

    # We'll collect counts for feedback
    added = {'tipos_cambio': 0, 'categorias': 0, 'subcategorias': 0, 'comercios': 0, 'reglas': 0, 'updated_tipos': 0, 'updated_subcategorias': 0, 'updated_comercios': 0}

    # Tipos de cambio
    for t in data.get('tipos_cambio', []):
        moneda = t.get('moneda')
        valor = t.get('valor')
        if not moneda:
            continue
        existing = TipoCambio.query.filter_by(moneda=moneda).first()
        if existing:
            existing.valor = valor
            added['updated_tipos'] += 1
        else:
            db.session.add(TipoCambio(moneda=moneda, valor=valor))
            added['tipos_cambio'] += 1

    # Categorías
    for c in data.get('categorias', []):
        nombre = c.get('nombre')
        if not nombre:
            continue
        existe = Categoria.query.filter(func.lower(Categoria.nombre) == nombre.strip().lower()).first()
        if not existe:
            db.session.add(Categoria(nombre=nombre.strip()))
            added['categorias'] += 1

    db.session.flush()

    categoria_by_name = {
        c.nombre.strip().lower(): c
        for c in Categoria.query.order_by(Categoria.id).all()
    }

    # Subcategorías
    for s in data.get('subcategorias', []):
        nombre = (s.get('nombre') or '').strip()
        if not nombre:
            continue

        categoria = None
        categoria_id = s.get('categoria_id')
        if categoria_id:
            categoria = Categoria.query.get(categoria_id)
        if not categoria:
            categoria_nombre = (s.get('categoria_nombre') or '').strip().lower()
            if categoria_nombre:
                categoria = categoria_by_name.get(categoria_nombre)

        if not categoria:
            continue

        existing = Subcategoria.query.filter(
            func.lower(Subcategoria.nombre) == nombre.lower(),
            Subcategoria.categoria_id == categoria.id
        ).first()
        if existing:
            continue

        db.session.add(Subcategoria(nombre=nombre, categoria_id=categoria.id))
        added['subcategorias'] += 1

    db.session.flush()

    subcategoria_lookup = {
        (s.categoria_id, s.nombre.strip().lower()): s
        for s in Subcategoria.query.all()
    }

    # Comercios and reglas
    for cm in data.get('comercios', []):
        nombre = cm.get('nombre')
        if not nombre:
            continue
        comercio = Comercio.query.filter_by(nombre=nombre).first()
        # Resolve category: prefer matching by id, fallback to first category
        cat_id = cm.get('categoria_id')
        categoria = None
        if cat_id:
            categoria = Categoria.query.get(cat_id)
        if not categoria:
            categoria_nombre = (cm.get('categoria_nombre') or '').strip().lower()
            if categoria_nombre:
                categoria = categoria_by_name.get(categoria_nombre)
        if not categoria:
            categoria = Categoria.query.first()

        subcategoria = None
        subcategoria_id = cm.get('subcategoria_id')
        if subcategoria_id:
            subcategoria = Subcategoria.query.get(subcategoria_id)
        if not subcategoria:
            subcategoria_nombre = (cm.get('subcategoria_nombre') or '').strip().lower()
            if categoria and subcategoria_nombre:
                subcategoria = subcategoria_lookup.get((categoria.id, subcategoria_nombre))

        if comercio:
            # update fields
            comercio.tipo_contabilizacion = cm.get('tipo_contabilizacion', comercio.tipo_contabilizacion)
            if categoria:
                comercio.categoria_id = categoria.id
            comercio.subcategoria_id = subcategoria.id if subcategoria else None
            added['updated_comercios'] += 1
        else:
            newc = Comercio(
                nombre=nombre,
                categoria_id=(categoria.id if categoria else None) or (Categoria.query.first().id if Categoria.query.first() else None),
                subcategoria_id=subcategoria.id if subcategoria else None,
                tipo_contabilizacion=cm.get('tipo_contabilizacion') or 'gastos'
            )
            db.session.add(newc)
            db.session.flush()
            comercio = newc
            added['comercios'] += 1

        # reglas
        for r in cm.get('reglas', []):
            tipo = (r.get('tipo') or '').strip().lower()
            condiciones = _condiciones_desde_regla_import(r)
            if tipo not in ('incluir', 'excluir') or not condiciones:
                continue

            firma_nueva = _firma_condiciones(condiciones)
            existentes = Regla.query.filter_by(
                comercio_id=comercio.id, tipo=tipo
            ).options(joinedload(Regla.condiciones)).all()
            ya_existe = any(
                _firma_condiciones([
                    {'campo': c.campo, 'operador': c.operador, 'valor': c.valor,
                     'valor2': c.valor2, 'conector': c.conector, 'negar': c.negar}
                    for c in existente.condiciones
                ]) == firma_nueva
                for existente in existentes
            )
            if ya_existe:
                continue

            nueva_regla = Regla(comercio_id=comercio.id, tipo=tipo)
            for c in condiciones:
                nueva_regla.condiciones.append(ReglaCondicion(
                    orden=c['orden'], conector=c['conector'], negar=c['negar'],
                    campo=c['campo'], operador=c['operador'], valor=c['valor'], valor2=c.get('valor2'),
                ))
            # El nombre se deriva de las condiciones, ignorando cualquier
            # "descripcion" del archivo importado (puede venir de un export
            # antiguo con texto libre que ya no refleja la lógica real).
            nueva_regla.descripcion = describir_regla(nueva_regla)[:200]
            db.session.add(nueva_regla)
            added['reglas'] += 1

    # Commit all changes
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error al importar configuración: {e}', 'danger')
        return redirect(url_for('main.dashboard'))

    flash(f"Importación finalizada. Tipos añadidos: {added['tipos_cambio']}, actualizados: {added['updated_tipos']}; Categorías añadidas: {added['categorias']}; Subcategorías añadidas: {added['subcategorias']}, actualizadas: {added['updated_subcategorias']}; Comercios añadidos: {added['comercios']}, actualizados: {added['updated_comercios']}; Reglas añadidas: {added['reglas']}", 'success')
    return redirect(url_for('main.dashboard'))



@bp.route('/backup_database', methods=['POST'])
@login_required
def backup_database_now():
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        abort(403)

    try:
        backup_path = backup_database(current_app._get_current_object())
    except Exception as exc:
        flash(f'No se pudo crear el respaldo: {exc}', 'danger')
    else:
        flash(f'Respaldo creado en {backup_path}', 'success')

    return redirect(url_for('main.data_tools'))



@bp.route('/datos')
@login_required
def data_tools():
    # Admin-only page that exposes export/import controls in one place
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        abort(403)

    return render_template(
        'data_tools.html',
        backup_path=current_app.config.get('DATABASE_BACKUP_PATH', '')
    )
