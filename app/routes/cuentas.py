from flask import render_template, request, redirect, url_for, flash
from . import bp
from .. import db
from ..models import Cuenta, Movimiento
from ..models import User
from flask_login import login_required, current_user


@bp.route('/cuentas')
@login_required
def list_cuentas():
    # Support optional owner filter for admins
    selected_owner = request.args.get('owner_id', '')
    users = []
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        users = User.query.order_by(User.username).all()
        if selected_owner:
            cuentas = Cuenta.query.filter_by(user_id=int(selected_owner)).order_by(Cuenta.numero_cuenta).all()
        else:
            cuentas = Cuenta.query.order_by(Cuenta.numero_cuenta).all()
    else:
        cuentas = Cuenta.query.filter_by(user_id=current_user.id).order_by(Cuenta.numero_cuenta).all()
    # Precalcular conteo de movimientos por cuenta (solo movimientos del usuario filtrado o del admin segun selection)
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        # Si hay filtro de owner, limitar a ese usuario; si no, conteo global
        mov_query = db.session.query(Movimiento.cuenta_id, db.func.count(Movimiento.id)).group_by(Movimiento.cuenta_id)
        if selected_owner:
            mov_query = mov_query.filter(Movimiento.user_id == int(selected_owner))
    else:
        mov_query = db.session.query(Movimiento.cuenta_id, db.func.count(Movimiento.id))\
            .filter(Movimiento.user_id == current_user.id)\
            .group_by(Movimiento.cuenta_id)
    mov_counts = {cid: cnt for cid, cnt in mov_query.all()}
    for c in cuentas:
        c.movimientos_count = mov_counts.get(c.id, 0)
    return render_template('cuentas.html', cuentas=cuentas, users=users, selected_owner=selected_owner)


@bp.route('/cuentas/add', methods=['GET', 'POST'])
@login_required
def add_cuenta():
    # Obtener lista de usuarios para administradores
    users = []
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        users = User.query.order_by(User.username).all()
    
    if request.method == 'POST':
        banco = request.form.get('banco', '').strip()
        tipo_cuenta = request.form.get('tipo_cuenta', '').strip()
        numero_cuenta = request.form.get('numero_cuenta', '').strip()
        alias = request.form.get('alias', '').strip()
        titular = request.form.get('titular', '').strip()
        moneda = request.form.get('moneda', '').strip()
        user_id = request.form.get('user_id', '')

        if not (banco and tipo_cuenta and numero_cuenta and titular and moneda):
            flash('Todos los campos son obligatorios.', 'danger')
            return render_template('cuentas_add.html', users=users)

        # Validar unicidad número de cuenta
        if Cuenta.query.filter_by(numero_cuenta=numero_cuenta).first():
            flash('Ya existe una cuenta con ese número.', 'warning')
            return render_template('cuentas_add.html', users=users)

        nueva = Cuenta(
            banco=banco,
            tipo_cuenta=tipo_cuenta,
            numero_cuenta=numero_cuenta,
            alias=alias or None,
            titular=titular,
            moneda=moneda
        )
        
        # Asignar propietario
        if hasattr(current_user, 'is_admin') and current_user.is_admin():
            # Los administradores pueden asignar propietario específico
            if user_id:
                try:
                    nueva.user_id = int(user_id)
                except ValueError:
                    flash('Usuario inválido seleccionado.', 'warning')
                    return render_template('cuentas_add.html', users=users)
            else:
                nueva.user_id = None  # Sin asignar
        else:
            nueva.user_id = current_user.id  # Usuarios normales se asignan a sí mismos
        
        db.session.add(nueva)
        db.session.commit()
        flash('Cuenta añadida correctamente.', 'success')
        return redirect(url_for('main.list_cuentas'))

    return render_template('cuentas_add.html', users=users)


@bp.route('/cuentas/<int:cuenta_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_cuenta(cuenta_id):
    cuenta = Cuenta.query.get_or_404(cuenta_id)
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        if cuenta.user_id != current_user.id:
            flash('Acceso denegado', 'danger')
            return redirect(url_for('main.list_cuentas'))
    
    # Obtener lista de usuarios para administradores
    users = []
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        users = User.query.order_by(User.username).all()
    
    if request.method == 'POST':
        banco = request.form.get('banco', '').strip()
        tipo_cuenta = request.form.get('tipo_cuenta', '').strip()
        numero_cuenta = request.form.get('numero_cuenta', '').strip()
        alias = request.form.get('alias', '').strip()
        titular = request.form.get('titular', '').strip()
        moneda = request.form.get('moneda', '').strip()
        user_id = request.form.get('user_id', '')

        if not (banco and tipo_cuenta and numero_cuenta and titular and moneda):
            flash('Todos los campos son obligatorios.', 'danger')
            return render_template('cuentas_edit.html', cuenta=cuenta, users=users)

        # Verificar si el número de cuenta ya lo usa otra cuenta
        other = Cuenta.query.filter(Cuenta.numero_cuenta == numero_cuenta, Cuenta.id != cuenta.id).first()
        if other:
            flash('Otra cuenta ya usa ese número.', 'warning')
            return render_template('cuentas_edit.html', cuenta=cuenta, users=users)

        cuenta.banco = banco
        cuenta.tipo_cuenta = tipo_cuenta
        cuenta.numero_cuenta = numero_cuenta
        cuenta.alias = alias or None
        cuenta.titular = titular
        cuenta.moneda = moneda
        
        # Solo los administradores pueden cambiar el propietario
        if hasattr(current_user, 'is_admin') and current_user.is_admin() and user_id:
            try:
                cuenta.user_id = int(user_id) if user_id else None
            except ValueError:
                flash('Usuario inválido seleccionado.', 'warning')
                return render_template('cuentas_edit.html', cuenta=cuenta, users=users)
        
        db.session.commit()
        flash('Cuenta actualizada correctamente.', 'success')
        return redirect(url_for('main.list_cuentas'))

    return render_template('cuentas_edit.html', cuenta=cuenta, users=users)


@bp.route('/cuentas/<int:cuenta_id>/delete', methods=['POST'])
@login_required
def delete_cuenta(cuenta_id):
    cuenta = Cuenta.query.get_or_404(cuenta_id)
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        if cuenta.user_id != current_user.id:
            flash('Acceso denegado', 'danger')
            return redirect(url_for('main.list_cuentas'))
    # Comprobar si tiene movimientos asociados
    tiene_mov = Movimiento.query.filter_by(cuenta_id=cuenta.id).first()
    if tiene_mov:
        flash('No se puede eliminar la cuenta: tiene movimientos asociados.', 'warning')
        return redirect(url_for('main.list_cuentas'))

    db.session.delete(cuenta)
    db.session.commit()
    flash('Cuenta eliminada.', 'warning')
    return redirect(url_for('main.list_cuentas'))
