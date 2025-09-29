from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from . import bp
from ..models import Movimiento, Comercio, Regla, User
from ..utils.classifier import reclasificar_movimientos
from .. import db


@bp.route('/sin_clasificar', methods=['GET'])
@login_required
def sin_clasificar():
    # Obtener filtro de usuario seleccionado (solo para admins)
    selected_owner = request.args.get('owner_id', '')
    
    # Base de la consulta - movimientos sin comercio asignado
    query = Movimiento.query.filter_by(comercio_id=None)
    
    # Filtrar por owner: admin puede filtrar por owner_id; los usuarios normales ven solo lo suyo
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        # obtener lista de usuarios para el select
        users = User.query.order_by(User.username).all()
        if selected_owner:
            try:
                oid = int(selected_owner)
                query = query.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        users = []
        query = query.filter(Movimiento.user_id == current_user.id)
    
    movimientos = query.order_by(Movimiento.fecha.desc()).all()
    comercios = Comercio.query.order_by(Comercio.nombre).all()
    
    return render_template('sin_clasificar.html',
                           movimientos=movimientos,
                           comercios=comercios,
                           users=users,
                           selected_owner=selected_owner)


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



