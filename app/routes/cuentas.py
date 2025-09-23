from flask import render_template, request, redirect, url_for, flash
from . import bp
from .. import db
from ..models import Cuenta, Movimiento


@bp.route('/cuentas')
def list_cuentas():
    cuentas = Cuenta.query.order_by(Cuenta.numero_cuenta).all()
    return render_template('cuentas.html', cuentas=cuentas)


@bp.route('/cuentas/add', methods=['GET', 'POST'])
def add_cuenta():
    if request.method == 'POST':
        banco = request.form.get('banco', '').strip()
        tipo_cuenta = request.form.get('tipo_cuenta', '').strip()
        numero_cuenta = request.form.get('numero_cuenta', '').strip()
        titular = request.form.get('titular', '').strip()
        moneda = request.form.get('moneda', '').strip()

        if not (banco and tipo_cuenta and numero_cuenta and titular and moneda):
            flash('Todos los campos son obligatorios.', 'danger')
            return render_template('cuentas_add.html')

        # Validar unicidad número de cuenta
        if Cuenta.query.filter_by(numero_cuenta=numero_cuenta).first():
            flash('Ya existe una cuenta con ese número.', 'warning')
            return render_template('cuentas_add.html')

        nueva = Cuenta(
            banco=banco,
            tipo_cuenta=tipo_cuenta,
            numero_cuenta=numero_cuenta,
            titular=titular,
            moneda=moneda
        )
        db.session.add(nueva)
        db.session.commit()
        flash('Cuenta añadida correctamente.', 'success')
        return redirect(url_for('main.list_cuentas'))

    return render_template('cuentas_add.html')


@bp.route('/cuentas/<int:cuenta_id>/edit', methods=['GET', 'POST'])
def edit_cuenta(cuenta_id):
    cuenta = Cuenta.query.get_or_404(cuenta_id)
    if request.method == 'POST':
        banco = request.form.get('banco', '').strip()
        tipo_cuenta = request.form.get('tipo_cuenta', '').strip()
        numero_cuenta = request.form.get('numero_cuenta', '').strip()
        titular = request.form.get('titular', '').strip()
        moneda = request.form.get('moneda', '').strip()

        if not (banco and tipo_cuenta and numero_cuenta and titular and moneda):
            flash('Todos los campos son obligatorios.', 'danger')
            return render_template('cuentas_edit.html', cuenta=cuenta)

        # Verificar si el número de cuenta ya lo usa otra cuenta
        other = Cuenta.query.filter(Cuenta.numero_cuenta == numero_cuenta, Cuenta.id != cuenta.id).first()
        if other:
            flash('Otra cuenta ya usa ese número.', 'warning')
            return render_template('cuentas_edit.html', cuenta=cuenta)

        cuenta.banco = banco
        cuenta.tipo_cuenta = tipo_cuenta
        cuenta.numero_cuenta = numero_cuenta
        cuenta.titular = titular
        cuenta.moneda = moneda
        db.session.commit()
        flash('Cuenta actualizada correctamente.', 'success')
        return redirect(url_for('main.list_cuentas'))

    return render_template('cuentas_edit.html', cuenta=cuenta)


@bp.route('/cuentas/<int:cuenta_id>/delete', methods=['POST'])
def delete_cuenta(cuenta_id):
    cuenta = Cuenta.query.get_or_404(cuenta_id)
    # Comprobar si tiene movimientos asociados
    tiene_mov = Movimiento.query.filter_by(cuenta_id=cuenta.id).first()
    if tiene_mov:
        flash('No se puede eliminar la cuenta: tiene movimientos asociados.', 'warning')
        return redirect(url_for('main.list_cuentas'))

    db.session.delete(cuenta)
    db.session.commit()
    flash('Cuenta eliminada.', 'warning')
    return redirect(url_for('main.list_cuentas'))
