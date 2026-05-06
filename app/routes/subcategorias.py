from flask import render_template, request, redirect, url_for, flash
from . import bp
from .. import db
from ..models import Categoria, Comercio, Movimiento, Subcategoria
from sqlalchemy import func
from flask_login import current_user, login_required


@bp.route('/subcategorias')
@login_required
def list_subcategorias():
    q_name = request.args.get('q_name', '').strip()
    owner_id = request.args.get('owner_id', type=int)

    counts_subq = db.session.query(
        Comercio.subcategoria_id.label('subcategoria_id'),
        func.count(Comercio.id).label('comercios_count')
    ).filter(Comercio.subcategoria_id.isnot(None)).group_by(Comercio.subcategoria_id).subquery()

    query = db.session.query(
        Subcategoria,
        func.coalesce(counts_subq.c.comercios_count, 0).label('comercios_count')
    ).join(Categoria, Categoria.id == Subcategoria.categoria_id).outerjoin(
        counts_subq, Subcategoria.id == counts_subq.c.subcategoria_id
    )

    if q_name:
        query = query.filter(Subcategoria.nombre.ilike(f"%{q_name}%"))

    rows = query.order_by(Categoria.nombre, Subcategoria.nombre).all()
    subcategorias = [{'subcategoria': r[0], 'comercios_count': r[1]} for r in rows]

    mov_query = db.session.query(Subcategoria.id, func.count(Movimiento.id))
    mov_query = mov_query.join(Comercio, Comercio.subcategoria_id == Subcategoria.id)
    if hasattr(current_user, 'is_admin') and current_user.is_admin() and owner_id:
        mov_query = mov_query.filter(Movimiento.user_id == owner_id)
    else:
        mov_query = mov_query.filter(Movimiento.user_id == current_user.id)
    mov_counts = {row[0]: row[1] for row in mov_query.group_by(Subcategoria.id).all()}

    for entry in subcategorias:
        subcategoria = entry['subcategoria']
        entry['movimientos_count'] = mov_counts.get(subcategoria.id, 0)

    filters = {'q_name': q_name, 'owner_id': owner_id or ''}
    return render_template('subcategorias.html', subcategorias=subcategorias, filters=filters)


@bp.route('/subcategorias/add', methods=['GET', 'POST'])
@login_required
def add_subcategoria():
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        categoria_id = request.form.get('categoria_id', type=int)
        if not nombre:
            flash('El nombre no puede quedar vacío.', 'danger')
        elif categoria_id is None:
            flash('Debes seleccionar una categoría.', 'danger')
        elif Subcategoria.query.filter_by(nombre=nombre, categoria_id=categoria_id).first():
            flash('Ya existe una subcategoría con ese nombre en esa categoría.', 'warning')
        else:
            nueva = Subcategoria(nombre=nombre, categoria_id=categoria_id)
            db.session.add(nueva)
            db.session.commit()
            flash('Subcategoría agregada correctamente.', 'success')
            # Redirigir de vuelta a la página de edición de categoría si viene de ahí
            referrer = request.referrer
            if referrer and f'/categorias/{categoria_id}/edit' in referrer:
                return redirect(url_for('main.edit_categoria', categoria_id=categoria_id))
            return redirect(url_for('main.list_subcategorias'))
    return render_template('subcategorias_add.html', categorias=categorias)


@bp.route('/subcategorias/<int:subcategoria_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_subcategoria(subcategoria_id):
    subcategoria = Subcategoria.query.get_or_404(subcategoria_id)
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        categoria_id = request.form.get('categoria_id', type=int) or subcategoria.categoria_id
        if not nombre:
            flash('El nombre no puede quedar vacío.', 'danger')
        elif Subcategoria.query.filter(Subcategoria.nombre == nombre, Subcategoria.categoria_id == categoria_id, Subcategoria.id != subcategoria.id).first():
            flash('Ya existe otra subcategoría con ese nombre en esa categoría.', 'warning')
        else:
            subcategoria.nombre = nombre
            subcategoria.categoria_id = categoria_id
            db.session.commit()
            flash('Subcategoría actualizada correctamente.', 'success')
            # Redirigir de vuelta a la página de edición de categoría si viene de ahí
            referrer = request.referrer
            if referrer and f'/categorias/{categoria_id}/edit' in referrer:
                return redirect(url_for('main.edit_categoria', categoria_id=categoria_id))
            return redirect(url_for('main.list_subcategorias'))
    return render_template('subcategorias_edit.html', subcategoria=subcategoria, categorias=categorias)


@bp.route('/subcategorias/<int:subcategoria_id>/delete', methods=['POST'])
@login_required
def delete_subcategoria(subcategoria_id):
    subcategoria = Subcategoria.query.get_or_404(subcategoria_id)
    categoria_id = subcategoria.categoria_id
    Comercio.query.filter_by(subcategoria_id=subcategoria.id).update({Comercio.subcategoria_id: None})
    db.session.delete(subcategoria)
    db.session.commit()
    flash('Subcategoría eliminada.', 'warning')
    # Redirigir de vuelta a la página de edición de categoría si viene de ahí
    referrer = request.referrer
    if referrer and f'/categorias/{categoria_id}/edit' in referrer:
        return redirect(url_for('main.edit_categoria', categoria_id=categoria_id))
    return redirect(url_for('main.list_subcategorias'))