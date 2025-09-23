from flask import render_template, request, redirect, url_for, flash
from . import bp
from .. import db
from ..models import Categoria


@bp.route('/categorias')
def list_categorias():
    categorias = Categoria.query.all()
    return render_template('categorias.html', categorias=categorias)


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
