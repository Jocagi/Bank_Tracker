from flask import render_template, request, redirect, url_for, flash
from . import bp
from .. import db
from ..models import Comercio, Regla, Categoria
from ..utils.classifier import reclasificar_movimientos


@bp.route('/comercios')
def list_comercios():
    #Obterner todos los comercios y sus reglas
    comercios = Comercio.query.all()
    for comercio in comercios:
        # Cargar reglas para cada comercio
        comercio.reglas = Regla.query.filter_by(comercio_id=comercio.id).all()
    # Ordenar por nombre
    comercios.sort(key=lambda c: c.nombre.lower())
    return render_template('comercios.html', comercios=comercios)


@bp.route('/comercios/add', methods=['GET', 'POST'])
def add_comercio():
    categorias = Categoria.query.all()
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
    return render_template('comercios_add.html', categorias=categorias)


@bp.route('/comercios/<int:comercio_id>/edit', methods=['GET', 'POST'])
def edit_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    categorias = Categoria.query.all()
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
