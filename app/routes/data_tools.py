from flask import render_template, request, flash, redirect, url_for, Response, abort
from sqlalchemy import func
from .. import db
from ..models import Comercio, Categoria, TipoCambio, Regla
from . import bp
from flask_login import login_required, current_user
import json


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

    # Comercios + reglas
    comercios = []
    for cm in Comercio.query.order_by(Comercio.nombre).all():
        reglas = []
        for r in cm.reglas:
            reglas.append({
                'id': r.id,
                'descripcion': r.descripcion,
                'tipo': r.tipo,
                'criterio': r.criterio
            })
        comercios.append({
            'id': cm.id,
            'nombre': cm.nombre,
            'categoria_id': cm.categoria_id,
            'tipo_contabilizacion': cm.tipo_contabilizacion,
            'reglas': reglas
        })

    payload = {
        'tipos_cambio': tipos,
        'categorias': categorias,
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
    added = {'tipos_cambio': 0, 'categorias': 0, 'comercios': 0, 'reglas': 0, 'updated_tipos': 0, 'updated_comercios': 0}

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
            categoria = Categoria.query.first()

        if comercio:
            # update fields
            comercio.tipo_contabilizacion = cm.get('tipo_contabilizacion', comercio.tipo_contabilizacion)
            if categoria:
                comercio.categoria_id = categoria.id
            added['updated_comercios'] += 1
        else:
            newc = Comercio(
                nombre=nombre,
                categoria_id=(categoria.id if categoria else None) or (Categoria.query.first().id if Categoria.query.first() else None),
                tipo_contabilizacion=cm.get('tipo_contabilizacion') or 'gastos'
            )
            db.session.add(newc)
            db.session.flush()
            comercio = newc
            added['comercios'] += 1

        # reglas
        for r in cm.get('reglas', []):
            desc = r.get('descripcion') or ''
            tipo = r.get('tipo') or ''
            criterio = r.get('criterio') or ''
            if not desc and not criterio:
                continue
            exists_rule = Regla.query.filter_by(comercio_id=comercio.id, descripcion=desc, tipo=tipo, criterio=criterio).first()
            if not exists_rule:
                db.session.add(Regla(comercio_id=comercio.id, descripcion=desc, tipo=tipo, criterio=criterio))
                added['reglas'] += 1

    # Commit all changes
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error al importar configuración: {e}', 'danger')
        return redirect(url_for('main.dashboard'))

    flash(f"Importación finalizada. Tipos añadidos: {added['tipos_cambio']}, actualizados: {added['updated_tipos']}; Categorías añadidas: {added['categorias']}; Comercios añadidos: {added['comercios']}, actualizados: {added['updated_comercios']}; Reglas añadidas: {added['reglas']}", 'success')
    return redirect(url_for('main.dashboard'))



@bp.route('/datos')
@login_required
def data_tools():
    # Admin-only page that exposes export/import controls in one place
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        abort(403)

    return render_template('data_tools.html')
