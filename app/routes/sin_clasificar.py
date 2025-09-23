from flask import render_template, request, redirect, url_for, flash
from . import bp
from ..models import Movimiento, Comercio, Regla
from ..utils.classifier import reclasificar_movimientos
from .. import db


@bp.route('/sin_clasificar', methods=['GET'])
def sin_clasificar():
    movimientos = Movimiento.query.filter_by(comercio_id=None).all()
    comercios   = Comercio.query.order_by(Comercio.nombre).all()
    return render_template('sin_clasificar.html',
                           movimientos=movimientos,
                           comercios=comercios)


@bp.route('/sin_clasificar/assign', methods=['POST'])
def assign_movimiento_rule():
    mov_id     = request.form.get('movimiento_id')
    comercio_id= request.form.get('comercio_id')
    movimiento = Movimiento.query.get_or_404(mov_id)
    comercio   = Comercio.query.get_or_404(comercio_id)

    # Crear regla "incluir" usando la descripción como criterio (escapada para regex)
    nueva_regla = Regla(
        comercio_id = comercio.id,
        descripcion = f"Automática: {movimiento.descripcion}",
        tipo        = 'incluir',
        criterio    = movimiento.descripcion
    )
    db.session.add(nueva_regla)
    db.session.commit()

    # Re-clasificar todos los movimientos
    reclasificar_movimientos()

    flash('Se ha añadido la regla y reclasificado los movimientos.', 'success')
    return redirect(url_for('main.edit_comercio', comercio_id=comercio.id))


@bp.route('/movimiento/<int:mov_id>/asignar', methods=['POST'])
def asignar_movimiento(mov_id):
    mov = Movimiento.query.get_or_404(mov_id)
    comercio_id = request.form.get('comercio_id')
    mov.comercio_id = comercio_id
    db.session.commit()
    flash('Movimiento clasificado manualmente.', 'success')
    return redirect(url_for('main.sin_clasificar'))
