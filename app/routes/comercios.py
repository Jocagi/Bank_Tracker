from flask import render_template, request, redirect, url_for, flash
from . import bp
from .. import db
from ..models import Comercio, Regla, Categoria, Movimiento
from flask_login import current_user
from ..utils.classifier import reclasificar_movimientos
from sqlalchemy.orm import joinedload
import re


def format_sentence_case(text):
    """Convierte un texto a formato de oración (primera letra mayúscula, resto minúscula)"""
    if not text:
        return text
    # Limpiar caracteres especiales y espacios extra
    text = re.sub(r'[^\w\s]', '', text).strip()
    # Convertir a formato de oración
    return text.capitalize()


@bp.route('/comercios')
def list_comercios():
    # Obtener todos los comercios y sus reglas
    # Filtros desde query string
    nombre_q = request.args.get('q_name', '').strip()
    categoria_id = request.args.get('categoria_id', type=int)
    tipo = request.args.get('tipo', '').strip()
    regla_q = request.args.get('regla', '').strip()
    owner_id = request.args.get('owner_id', type=int)

    # Construir consulta dinámica
    query = Comercio.query
    if categoria_id:
        query = query.filter(Comercio.categoria_id == categoria_id)
    if tipo:
        query = query.filter(Comercio.tipo_contabilizacion == tipo)
    if nombre_q:
        query = query.filter(Comercio.nombre.ilike(f"%{nombre_q}%"))
    if regla_q:
        # Buscar dentro de las reglas (descripcion, criterio o tipo)
        query = query.join(Regla).filter(
            (Regla.descripcion.ilike(f"%{regla_q}%")) |
            (Regla.criterio.ilike(f"%{regla_q}%")) |
            (Regla.tipo.ilike(f"%{regla_q}%"))
        ).distinct()

    # Eager-load reglas y categoria para evitar N+1
    # Añadir un conteo de movimientos por comercio (LEFT JOIN semantics)
    comercios = query.options(joinedload(Comercio.reglas), joinedload(Comercio.categoria)).all()

    # Precalcular counts para evitar N+1
    # Conteo de movimientos: si admin puede filtrar por owner_id, sino solo del usuario actual
    movimiento_query = db.session.query(Movimiento.comercio_id, db.func.count(Movimiento.id))
    if hasattr(current_user, 'is_admin') and current_user.is_admin() and owner_id:
        movimiento_query = movimiento_query.filter(Movimiento.user_id == owner_id)
    else:
        movimiento_query = movimiento_query.filter(Movimiento.user_id == current_user.id)
    movimiento_counts = {row[0]: row[1] for row in movimiento_query.group_by(Movimiento.comercio_id).all()}
    for c in comercios:
        c.movimientos_count = movimiento_counts.get(c.id, 0)

    # Ordenar por nombre
    comercios.sort(key=lambda c: c.nombre.lower())

    # Pasar listas auxiliares (categorias) y valores de filtro actuales para la plantilla
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    filters = {
        'q_name': nombre_q,
        'categoria_id': categoria_id or '',
        'tipo': tipo,
        'regla': regla_q,
        'owner_id': owner_id or ''
    }
    return render_template('comercios.html', comercios=comercios, categorias=categorias, filters=filters)


@bp.route('/comercios/add', methods=['GET', 'POST'])
def add_comercio():
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    
    # Obtener datos pre-llenados de la URL
    pre_nombre = format_sentence_case(request.args.get('nombre', ''))
    pre_regla = request.args.get('regla', '')
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        categoria_id = request.form['categoria_id']
        tipo_contabilizacion  = request.form['tipo_contabilizacion']

        # Crear nuevo comercio
        nuevo_comercio = Comercio(
            nombre=nombre,
            categoria_id=categoria_id,
            tipo_contabilizacion=tipo_contabilizacion
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
    return render_template('comercios_add.html', categorias=categorias, pre_nombre=pre_nombre, pre_regla=pre_regla)


@bp.route('/comercios/<int:comercio_id>/edit', methods=['GET', 'POST'])
def edit_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    if request.method == 'POST':
        comercio.nombre = request.form['nombre']
        comercio.categoria_id = request.form['categoria_id']
        comercio.tipo_contabilizacion = request.form['tipo_contabilizacion']
        
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
        
        # Re-clasificar todos los movimientos tras modificar reglas
        reclasificar_movimientos()

        flash('Comercio actualizado', 'success')
        return redirect(url_for('main.list_comercios'))
    return render_template('comercios_edit.html', comercio=comercio, categorias=categorias)


@bp.route('/comercios/<int:comercio_id>/delete', methods=['POST'])
def delete_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    db.session.delete(comercio)
    db.session.commit()
    reclasificar_movimientos()
    flash('Comercio eliminado', 'warning')
    return redirect(url_for('main.list_comercios'))
