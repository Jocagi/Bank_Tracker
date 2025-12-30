from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from . import bp
from .. import db
from ..models import PresupuestoRegla as Regla, PresupuestoPlan, Categoria
from ..forms import RuleForm, PlanForm
from datetime import date, datetime


@bp.route('/presupuestos')
@login_required
def list_presupuestos():
    # Listar planes de presupuesto del usuario
    planes = PresupuestoPlan.query.filter_by(user_id=current_user.id).order_by(PresupuestoPlan.active.desc(), PresupuestoPlan.fecha_inicio.desc()).all()
    return render_template('presupuesto_planes.html', planes=planes)


@bp.route('/presupuestos/add', methods=['GET', 'POST'])
@login_required
def add_plan():
    form = PlanForm()
    if request.method == 'GET':
        hoy = date.today()
        primer_dia = date(hoy.year, hoy.month, 1)
        form.fecha_inicio.data = primer_dia

    if form.validate_on_submit():
        p = PresupuestoPlan(
            user_id=current_user.id,
            nombre=form.nombre.data.strip(),
            fecha_inicio=form.fecha_inicio.data,
            active=bool(form.active.data),
            created_at=datetime.utcnow()
        )
        db.session.add(p)
        db.session.commit()
        flash('Plan de presupuesto creado.', 'success')
        return redirect(url_for('main.list_presupuestos'))

    return render_template('presupuesto_plan_form.html', form=form, action='Agregar')


@bp.route('/presupuestos/planes/<int:plan_id>', methods=['GET'])
@login_required
def view_plan(plan_id):
    plan = PresupuestoPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    reglas = Regla.query.filter_by(presupuesto_id=plan.id).order_by(Regla.fecha_inicio.desc()).all()
    # categorias map
    categorias = {c.id: c.nombre for c in Categoria.query.all()}
    return render_template('presupuesto_plan_detail.html', plan=plan, reglas=reglas, categorias=categorias)


@bp.route('/presupuestos/planes/<int:plan_id>/reglas/add', methods=['GET', 'POST'])
@login_required
def add_regla(plan_id):
    plan = PresupuestoPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    form = RuleForm()
    cats = Categoria.query.order_by(Categoria.nombre).all()
    form.categoria_id.choices = [(c.id, c.nombre) for c in cats]

    if request.method == 'GET':
        hoy = date.today()
        form.fecha_inicio.data = date(hoy.year, hoy.month, 1)

    if form.validate_on_submit():
        r = Regla(
            presupuesto_id=plan.id,
            user_id=current_user.id,
            categoria_id=form.categoria_id.data,
            tipo=form.tipo.data or 'inesperado',
            monto=float(form.monto.data),
            fecha_inicio=form.fecha_inicio.data,
            created_at=datetime.utcnow()
        )
        db.session.add(r)
        db.session.commit()
        flash('Regla agregada al plan.', 'success')
        return redirect(url_for('main.view_plan', plan_id=plan.id))

    return render_template('presupuesto_form.html', form=form, action='Agregar')


@bp.route('/presupuestos/planes/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plan(plan_id):
    plan = PresupuestoPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    form = PlanForm()
    if request.method == 'GET':
        form.nombre.data = plan.nombre
        form.fecha_inicio.data = plan.fecha_inicio
        form.active.data = plan.active

    if form.validate_on_submit():
        plan.nombre = form.nombre.data.strip()
        plan.fecha_inicio = form.fecha_inicio.data
        plan.active = bool(form.active.data)
        db.session.commit()
        flash('Plan actualizado.', 'success')
        return redirect(url_for('main.list_presupuestos'))

    return render_template('presupuesto_plan_form.html', form=form, action='Editar')


@bp.route('/presupuestos/planes/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_plan(plan_id):
    plan = PresupuestoPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    # Remove related rules first
    Regla.query.filter_by(presupuesto_id=plan.id).delete()
    db.session.delete(plan)
    db.session.commit()
    flash('Plan eliminado.', 'warning')
    return redirect(url_for('main.list_presupuestos'))


@bp.route('/presupuestos/reglas/<int:regla_id>/delete', methods=['POST'])
@login_required
def delete_regla(regla_id):
    regla = Regla.query.get_or_404(regla_id)
    # only owner can delete
    if regla.user_id != current_user.id:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.list_presupuestos'))
    plan_id = regla.presupuesto_id
    db.session.delete(regla)
    db.session.commit()
    flash('Regla eliminada.', 'warning')
    if plan_id:
        return redirect(url_for('main.view_plan', plan_id=plan_id))
    return redirect(url_for('main.list_presupuestos'))


@bp.route('/presupuestos/reglas/<int:regla_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_regla(regla_id):
    regla = Regla.query.get_or_404(regla_id)
    if regla.user_id != current_user.id:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.list_presupuestos'))

    form = RuleForm()
    cats = Categoria.query.order_by(Categoria.nombre).all()
    form.categoria_id.choices = [(c.id, c.nombre) for c in cats]

    if request.method == 'GET':
        form.categoria_id.data = regla.categoria_id
        form.tipo.data = regla.tipo
        form.monto.data = regla.monto
        form.fecha_inicio.data = regla.fecha_inicio

    if form.validate_on_submit():
        # Create new rule effective from given date (immutable history)
        new_r = Regla(
            presupuesto_id=regla.presupuesto_id,
            user_id=current_user.id,
            categoria_id=form.categoria_id.data,
            tipo=form.tipo.data or 'inesperado',
            monto=float(form.monto.data),
            fecha_inicio=form.fecha_inicio.data,
            created_at=datetime.utcnow()
        )
        db.session.add(new_r)
        db.session.commit()
        flash('Regla actualizada (nuevo registro creado).', 'success')
        return redirect(url_for('main.view_plan', plan_id=regla.presupuesto_id))

    return render_template('presupuesto_form.html', form=form, action='Editar')
