from flask import render_template, request, redirect, url_for, flash
from . import bp
from .. import db
from ..models import TipoCambio


@bp.route('/tipos_cambio')
def list_tipos_cambio():
    tipos = TipoCambio.query.order_by(TipoCambio.moneda).all()
    return render_template('tipos_cambio.html', tipos=tipos)


@bp.route('/tipos_cambio/add', methods=['GET','POST'])
def add_tipo_cambio():
    if request.method == 'POST':
        moneda = request.form['moneda'].strip().upper()
        try:
            valor = float(request.form['valor'])
        except ValueError:
            flash('Valor de tipo de cambio inválido.', 'danger')
            return redirect(url_for('main.add_tipo_cambio'))
        if not moneda:
            flash('La moneda no puede quedar vacía.', 'danger')
        elif TipoCambio.query.filter_by(moneda=moneda).first():
            flash('Ya existe ese tipo de cambio.', 'warning')
        else:
            tc = TipoCambio(moneda=moneda, valor=valor)
            db.session.add(tc)
            db.session.commit()
            flash('Tipo de cambio agregado.', 'success')
            return redirect(url_for('main.list_tipos_cambio'))
    return render_template('tipo_cambio_add.html')


@bp.route('/tipos_cambio/<int:tc_id>/edit', methods=['GET','POST'])
def edit_tipo_cambio(tc_id):
    tc = TipoCambio.query.get_or_404(tc_id)
    if request.method == 'POST':
        try:
            valor = float(request.form['valor'])
        except ValueError:
            flash('Valor de tipo de cambio inválido.', 'danger')
            return redirect(url_for('main.edit_tipo_cambio', tc_id=tc.id))
        tc.valor = valor
        db.session.commit()
        flash('Tipo de cambio actualizado.', 'success')
        return redirect(url_for('main.list_tipos_cambio'))
    return render_template('tipo_cambio_edit.html', tc=tc)


@bp.route('/tipos_cambio/<int:tc_id>/delete', methods=['POST'])
def delete_tipo_cambio(tc_id):
    tc = TipoCambio.query.get_or_404(tc_id)
    db.session.delete(tc)
    db.session.commit()
    flash('Tipo de cambio eliminado.', 'warning')
    return redirect(url_for('main.list_tipos_cambio'))
