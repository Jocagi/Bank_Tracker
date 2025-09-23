from datetime import datetime
from flask import render_template, request, flash
from sqlalchemy import func
from .. import db
from ..models import Comercio, Categoria, Movimiento, TipoCambio
from . import bp


@bp.route('/dashboard')
def dashboard():
    # ————————————————————————————————————————
    # 1) Leer filtros desde la query string
    start   = request.args.get('start_date', '')
    end     = request.args.get('end_date', '')
    cat_id  = request.args.get('category_id', '')

    d_start = d_end = None
    if start:
        try:
            d_start = datetime.strptime(start, '%Y-%m-%d').date()
        except ValueError:
            flash('Fecha “Desde” inválida', 'warning')
    if end:
        try:
            d_end = datetime.strptime(end, '%Y-%m-%d').date()
        except ValueError:
            flash('Fecha “Hasta” inválida', 'warning')

    # ————————————————————————————————————————
    # 2) Lista de categorías para el dropdown
    categorias = Categoria.query.order_by(Categoria.nombre).all()

    # ————————————————————————————————————————
    # 3) Gastos por Comercio (GTQ)
    commerce_q = (
        db.session.query(
            Comercio.nombre,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .order_by(func.sum(Movimiento.monto * TipoCambio.valor).asc())
    )
    if d_start:
        commerce_q = commerce_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        commerce_q = commerce_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        commerce_q = commerce_q.join(Categoria)\
                               .filter(Categoria.id == int(cat_id))

    commerce_data = commerce_q.group_by(Comercio.id).all()
    if commerce_data:
        commerce_labels, commerce_values = zip(*commerce_data)
    else:
        commerce_labels = commerce_values = []

    commerce_table = [
        (lbl, abs(total)) for lbl, total in commerce_data
    ]

    # ————————————————————————————————————————
    # 4) Gastos por Categoría (GTQ)
    cat_q = (
        db.session.query(
            Categoria.nombre,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Comercio, Comercio.categoria_id == Categoria.id)
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .order_by(func.sum(Movimiento.monto * TipoCambio.valor).asc())
    )
    if d_start:
        cat_q = cat_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        cat_q = cat_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        cat_q = cat_q.filter(Categoria.id == int(cat_id))

    cat_data = cat_q.group_by(Categoria.id).all()
    if cat_data:
        cat_labels, cat_values = zip(*cat_data)
    else:
        cat_labels = cat_values = []

    category_table = [
        (lbl, abs(total)) for lbl, total in cat_data
    ]

    # ————————————————————————————————————————
    # 5) Evolución Mensual de Gastos (GTQ)
    # label the month column so we can group/order by the labeled column (not a plain string)
    mes = func.strftime('%Y-%m', Movimiento.fecha).label('mes')
    month_q = (
        db.session.query(
            mes,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
    )
    if d_start:
        month_q = month_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        month_q = month_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        month_q = month_q.filter(Comercio.categoria_id == int(cat_id))

    month_data = month_q.group_by(mes).order_by(mes).all()
    if month_data:
        month_labels, raw_vals = zip(*month_data)
        month_values = [abs(v) for v in raw_vals]
    else:
        month_labels = month_values = []

    # ————————————————————————————————————————
    # 5.b) Evolución Mensual de Ingresos (GTQ)
    income_month_q = (
        db.session.query(
            mes,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'ingresos')
    )
    if d_start:
        income_month_q = income_month_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        income_month_q = income_month_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        # If category is selected, restrict by comercio's category (same as gastos)
        income_month_q = income_month_q.filter(Comercio.categoria_id == int(cat_id))

    income_month_data = income_month_q.group_by(mes).order_by(mes).all()

    # Align income series with months from expenses: create a dict for quick lookup
    income_by_month = {m: abs(v) for m, v in income_month_data} if income_month_data else {}

    # Build month_income_values aligned with month_labels (expenses). If there are months with incomes
    # not present in expenses, include them by extending labels and values so both series share same x-axis.
    if month_labels:
        # Ensure month_labels is a list
        month_labels = list(month_labels)
        month_income_values = [income_by_month.get(m, 0) for m in month_labels]
        # Also check for income months not in month_labels and append them
        extra_income_months = [m for m in income_by_month.keys() if m not in month_labels]
        if extra_income_months:
            extra_months_sorted = sorted(extra_income_months)
            for m in extra_months_sorted:
                month_labels.append(m)
                month_values.append(0)
                month_income_values.append(income_by_month.get(m, 0))
    else:
        # No expense months, but maybe income months exist
        if income_month_data:
            month_labels, income_vals = zip(*income_month_data)
            month_labels = list(month_labels)
            month_values = [0 for _ in income_vals]
            month_income_values = [abs(v) for v in income_vals]
        else:
            month_labels = month_values = month_income_values = []

    # ————————————————————————————————————————
    # 6) **Ingresos por Comercio (GTQ)**
    income_q = (
        db.session.query(
            Comercio.nombre,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'ingresos')
    )
    if d_start:
        income_q = income_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        income_q = income_q.filter(Movimiento.fecha <= d_end)

    income_data = income_q.group_by(Comercio.id).all()
    income_table = [
        (lbl, abs(total)) for lbl, total in income_data
    ]

    # ————————————————————————————————————————
    return render_template('dashboard.html',
        # Charts de gastos
        commerce_labels=list(commerce_labels),
        commerce_values=list(commerce_values),
        cat_labels=list(cat_labels),
        cat_values=list(cat_values),
        month_labels=list(month_labels),
        month_values=list(month_values),
        month_income_values=list(month_income_values),
        # Tablas de gastos
        commerce_table=commerce_table,
        category_table=category_table,
        # **Tabla de ingresos**
        income_table=income_table,
        # Filtros
        categorias=categorias,
        start_date=start,
        end_date=end,
        selected_cat=cat_id
    )
