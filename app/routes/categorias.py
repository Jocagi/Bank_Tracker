from flask import render_template, request, redirect, url_for, flash
from . import bp
from .. import db
from ..models import Categoria, Comercio, Movimiento
from sqlalchemy import func
from flask_login import current_user


@bp.route('/categorias')
def list_categorias():
    # Filtro por nombre desde query string
    q_name = request.args.get('q_name', '').strip()
    owner_id = request.args.get('owner_id', type=int)

    # Subquery para contar comercios por categoría
    counts_subq = db.session.query(
        Comercio.categoria_id.label('categoria_id'),
        func.count(Comercio.id).label('comercios_count')
    ).group_by(Comercio.categoria_id).subquery()

    # Construir consulta principal con outerjoin a subquery de conteos
    query = db.session.query(
        Categoria,
        func.coalesce(counts_subq.c.comercios_count, 0).label('comercios_count')
    ).outerjoin(counts_subq, Categoria.id == counts_subq.c.categoria_id)

    if q_name:
        query = query.filter(Categoria.nombre.ilike(f"%{q_name}%"))

    rows = query.order_by(Categoria.nombre).all()

    # Separar en listas (categoria, conteo)
    categorias = [{'categoria': r[0], 'comercios_count': r[1]} for r in rows]

    # Calcular movimientos por categoría (a través de Comercio.categoria_id)
    mov_query = db.session.query(Comercio.categoria_id, func.count(Movimiento.id))
    mov_query = mov_query.join(Movimiento, Movimiento.comercio_id == Comercio.id)
    if hasattr(current_user, 'is_admin') and current_user.is_admin() and owner_id:
        mov_query = mov_query.filter(Movimiento.user_id == owner_id)
    else:
        mov_query = mov_query.filter(Movimiento.user_id == current_user.id)
    mov_counts = {row[0]: row[1] for row in mov_query.group_by(Comercio.categoria_id).all()}

    for entry in categorias:
        cat = entry['categoria']
        entry['movimientos_count'] = mov_counts.get(cat.id, 0)

    filters = {'q_name': q_name, 'owner_id': owner_id or ''}
    return render_template('categorias.html', categorias=categorias, filters=filters)


@bp.route('/categorias/add', methods=['GET', 'POST'])
def add_categoria():
    if request.method == 'POST':
        nombre = request.form['nombre']
        nueva = Categoria(nombre=nombre)
        db.session.add(nueva)
        db.session.commit()
        flash('Categoría agregada correctamente.', 'success')
        return redirect(url_for('main.list_categorias'))
    return render_template('categorias_add.html')


@bp.route('/categorias/<int:categoria_id>/edit', methods=['GET', 'POST'])
def edit_categoria(categoria_id):
    categoria = Categoria.query.get_or_404(categoria_id)
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        if not nombre:
            flash('El nombre no puede quedar vacío.', 'danger')
        elif Categoria.query.filter(Categoria.nombre==nombre, Categoria.id!=categoria.id).first():
            flash('Ya existe otra categoría con ese nombre.', 'warning')
        else:
            categoria.nombre = nombre
            db.session.commit()
            flash('Categoría actualizada correctamente.', 'success')
            return redirect(url_for('main.list_categorias'))
    return render_template('categorias_edit.html', categoria=categoria)


@bp.route('/categorias/<int:categoria_id>/delete', methods=['POST'])
def delete_categoria(categoria_id):
    categoria = Categoria.query.get_or_404(categoria_id)
    db.session.delete(categoria)
    db.session.commit()
    flash('Categoría eliminada.', 'warning')
    return redirect(url_for('main.list_categorias'))
