from datetime import datetime
from flask import render_template, request, flash
from sqlalchemy import func
from .. import db
from ..models import Comercio, Categoria, Movimiento, TipoCambio, User
from . import bp
from flask_login import login_required, current_user


@bp.route('/dashboard')
@login_required
def dashboard():
    # ————————————————————————————————————————
    # 1) Leer filtros desde la query string
    start   = request.args.get('start_date', '')
    end     = request.args.get('end_date', '')
    cat_id  = request.args.get('category_id', '')
    table_limit = request.args.get('table_limit', '10')  # Valor por defecto: 10

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

    # Lista de usuarios (solo necesaria si es admin)
    users = []
    owner_id = request.args.get('owner_id', '')
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        users = User.query.order_by(User.username).all()


    # ————————————————————————————————————————
    # 3) Gastos por Comercio (GTQ) - Incluye movimientos sin clasificar
    # Parte 1: Movimientos clasificados como gastos
    commerce_classified_q = (
        db.session.query(
            Comercio.nombre.label('nombre'),
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
    )
    
    # Parte 2: Movimientos sin clasificar (negativos = gastos)
    commerce_unclassified_q = (
        db.session.query(
            db.literal('No clasificado').label('nombre'),
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Movimiento.comercio_id.is_(None))
        .filter(Movimiento.monto < 0)  # Solo gastos (negativos)
    )
    # Aplicar filtros a ambas consultas
    # Filtrar por owner: si el usuario es admin puede seleccionar owner_id, si no -> su propio id
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                commerce_classified_q = commerce_classified_q.filter(Movimiento.user_id == oid)
                commerce_unclassified_q = commerce_unclassified_q.filter(Movimiento.user_id == oid)
            except ValueError:
                # ignore invalid owner_id
                pass
    else:
        commerce_classified_q = commerce_classified_q.filter(Movimiento.user_id == current_user.id)
        commerce_unclassified_q = commerce_unclassified_q.filter(Movimiento.user_id == current_user.id)

    # Aplicar filtros de fecha
    if d_start:
        commerce_classified_q = commerce_classified_q.filter(Movimiento.fecha >= d_start)
        commerce_unclassified_q = commerce_unclassified_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        commerce_classified_q = commerce_classified_q.filter(Movimiento.fecha <= d_end)
        commerce_unclassified_q = commerce_unclassified_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        commerce_classified_q = commerce_classified_q.join(Categoria)\
                                                   .filter(Categoria.id == int(cat_id))
        # Para no clasificados, si hay filtro de categoría, no incluirlos
        commerce_unclassified_q = None

    # Ejecutar consultas y combinar resultados
    commerce_classified_data = commerce_classified_q.group_by(Comercio.id).order_by(func.sum(Movimiento.monto * TipoCambio.valor).asc()).all()
    
    commerce_data = list(commerce_classified_data)
    
    if commerce_unclassified_q and not cat_id:  # Solo incluir no clasificados si no hay filtro de categoría
        commerce_unclassified_data = commerce_unclassified_q.all()
        if commerce_unclassified_data and commerce_unclassified_data[0][1] != 0:
            commerce_data.extend(commerce_unclassified_data)
    if commerce_data:
        commerce_labels, commerce_values = zip(*commerce_data)
    else:
        commerce_labels = commerce_values = []

    commerce_table = [
        (lbl, abs(total) if total is not None else 0) for lbl, total in commerce_data
    ]

    # ————————————————————————————————————————
    # 4) Gastos por Categoría (GTQ) - Incluye movimientos sin clasificar
    # Parte 1: Movimientos clasificados como gastos
    cat_classified_q = (
        db.session.query(
            Categoria.nombre.label('nombre'),
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Comercio, Comercio.categoria_id == Categoria.id)
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
    )
    
    # Parte 2: Movimientos sin clasificar (negativos = gastos)
    cat_unclassified_q = (
        db.session.query(
            db.literal('No clasificado').label('nombre'),
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Movimiento.comercio_id.is_(None))
        .filter(Movimiento.monto < 0)  # Solo gastos (negativos)
    )
    # Aplicar filtros a ambas consultas de categorías
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                cat_classified_q = cat_classified_q.filter(Movimiento.user_id == oid)
                cat_unclassified_q = cat_unclassified_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        cat_classified_q = cat_classified_q.filter(Movimiento.user_id == current_user.id)
        cat_unclassified_q = cat_unclassified_q.filter(Movimiento.user_id == current_user.id)
    
    if d_start:
        cat_classified_q = cat_classified_q.filter(Movimiento.fecha >= d_start)
        cat_unclassified_q = cat_unclassified_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        cat_classified_q = cat_classified_q.filter(Movimiento.fecha <= d_end)
        cat_unclassified_q = cat_unclassified_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        cat_classified_q = cat_classified_q.filter(Categoria.id == int(cat_id))
        # Para no clasificados, si hay filtro de categoría, no incluirlos
        cat_unclassified_q = None

    # Ejecutar consultas y combinar resultados
    cat_classified_data = cat_classified_q.group_by(Categoria.id).order_by(func.sum(Movimiento.monto * TipoCambio.valor).asc()).all()
    
    cat_data = list(cat_classified_data)
    
    if cat_unclassified_q and not cat_id:  # Solo incluir no clasificados si no hay filtro de categoría
        cat_unclassified_data = cat_unclassified_q.all()
        if cat_unclassified_data and cat_unclassified_data[0][1] != 0:
            cat_data.extend(cat_unclassified_data)
    if cat_data:
        cat_labels, cat_values = zip(*cat_data)
    else:
        cat_labels = cat_values = []

    category_table = [
        (lbl, abs(total) if total is not None else 0) for lbl, total in cat_data
    ]

    # ————————————————————————————————————————
    # 5) Evolución Mensual de Gastos (GTQ) - Incluye movimientos sin clasificar
    # label the month column so we can group/order by the labeled column (not a plain string)
    mes = func.strftime('%Y-%m', Movimiento.fecha).label('mes')
    
    # Parte 1: Movimientos clasificados como gastos
    month_classified_q = (
        db.session.query(
            mes,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
    )
    
    # Parte 2: Movimientos sin clasificar (negativos = gastos)
    month_unclassified_q = (
        db.session.query(
            mes,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Movimiento.comercio_id.is_(None))
        .filter(Movimiento.monto < 0)  # Solo gastos (negativos)
    )
    # Aplicar filtros a ambas consultas mensuales de gastos
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                month_classified_q = month_classified_q.filter(Movimiento.user_id == oid)
                month_unclassified_q = month_unclassified_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        month_classified_q = month_classified_q.filter(Movimiento.user_id == current_user.id)
        month_unclassified_q = month_unclassified_q.filter(Movimiento.user_id == current_user.id)
    
    if d_start:
        month_classified_q = month_classified_q.filter(Movimiento.fecha >= d_start)
        month_unclassified_q = month_unclassified_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        month_classified_q = month_classified_q.filter(Movimiento.fecha <= d_end)
        month_unclassified_q = month_unclassified_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        month_classified_q = month_classified_q.filter(Comercio.categoria_id == int(cat_id))
        # Para no clasificados, si hay filtro de categoría, no incluirlos
        month_unclassified_q = None

    # Ejecutar consultas y combinar resultados por mes
    month_classified_data = month_classified_q.group_by(mes).order_by(mes).all()
    month_data_dict = {m: total if total is not None else 0 for m, total in month_classified_data}
    
    if month_unclassified_q and not cat_id:  # Solo incluir no clasificados si no hay filtro de categoría
        month_unclassified_data = month_unclassified_q.group_by(mes).order_by(mes).all()
        for m, total in month_unclassified_data:
            total = total if total is not None else 0
            if m in month_data_dict:
                month_data_dict[m] += total
            else:
                month_data_dict[m] = total
    
    # Convertir de nuevo a lista ordenada
    month_data = [(m, total) for m, total in sorted(month_data_dict.items())]
    if month_data:
        month_labels, raw_vals = zip(*month_data)
        month_values = [abs(v) if v is not None else 0 for v in raw_vals]
    else:
        month_labels = month_values = []

    # ————————————————————————————————————————
    # 5.b) Evolución Mensual de Ingresos (GTQ) - Incluye movimientos sin clasificar
    # Parte 1: Movimientos clasificados como ingresos
    income_month_classified_q = (
        db.session.query(
            mes,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'ingresos')
    )
    
    # Parte 2: Movimientos sin clasificar (positivos = ingresos)
    income_month_unclassified_q = (
        db.session.query(
            mes,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Movimiento.comercio_id.is_(None))
        .filter(Movimiento.monto > 0)  # Solo ingresos (positivos)
    )
    # Aplicar filtros a ambas consultas mensuales de ingresos
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                income_month_classified_q = income_month_classified_q.filter(Movimiento.user_id == oid)
                income_month_unclassified_q = income_month_unclassified_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        income_month_classified_q = income_month_classified_q.filter(Movimiento.user_id == current_user.id)
        income_month_unclassified_q = income_month_unclassified_q.filter(Movimiento.user_id == current_user.id)
    
    if d_start:
        income_month_classified_q = income_month_classified_q.filter(Movimiento.fecha >= d_start)
        income_month_unclassified_q = income_month_unclassified_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        income_month_classified_q = income_month_classified_q.filter(Movimiento.fecha <= d_end)
        income_month_unclassified_q = income_month_unclassified_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        # If category is selected, restrict by comercio's category (same as gastos)
        income_month_classified_q = income_month_classified_q.filter(Comercio.categoria_id == int(cat_id))
        # Para no clasificados, si hay filtro de categoría, no incluirlos
        income_month_unclassified_q = None

    # Ejecutar consultas y combinar resultados por mes
    income_month_classified_data = income_month_classified_q.group_by(mes).order_by(mes).all()
    income_month_data_dict = {m: total if total is not None else 0 for m, total in income_month_classified_data}
    
    if income_month_unclassified_q and not cat_id:  # Solo incluir no clasificados si no hay filtro de categoría
        income_month_unclassified_data = income_month_unclassified_q.group_by(mes).order_by(mes).all()
        for m, total in income_month_unclassified_data:
            total = total if total is not None else 0
            if m in income_month_data_dict:
                income_month_data_dict[m] += total
            else:
                income_month_data_dict[m] = total
    
    # Convertir de nuevo a lista ordenada
    income_month_data = [(m, total) for m, total in sorted(income_month_data_dict.items())]

    # Align income series with months from expenses: create a dict for quick lookup
    income_by_month = {m: abs(v) if v is not None else 0 for m, v in income_month_data} if income_month_data else {}

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
            month_income_values = [abs(v) if v is not None else 0 for v in income_vals]
        else:
            month_labels = month_values = month_income_values = []

    # ————————————————————————————————————————
    # 6) **Ingresos por Comercio (GTQ)** - Incluye movimientos sin clasificar
    # Parte 1: Movimientos clasificados como ingresos
    income_classified_q = (
        db.session.query(
            Comercio.nombre.label('nombre'),
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'ingresos')
    )
    
    # Parte 2: Movimientos sin clasificar (positivos = ingresos)
    income_unclassified_q = (
        db.session.query(
            db.literal('No clasificado').label('nombre'),
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Movimiento.comercio_id.is_(None))
        .filter(Movimiento.monto > 0)  # Solo ingresos (positivos)
    )
    
    # Aplicar filtros a ambas consultas de ingresos
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                income_classified_q = income_classified_q.filter(Movimiento.user_id == oid)
                income_unclassified_q = income_unclassified_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        income_classified_q = income_classified_q.filter(Movimiento.user_id == current_user.id)
        income_unclassified_q = income_unclassified_q.filter(Movimiento.user_id == current_user.id)
    
    if d_start:
        income_classified_q = income_classified_q.filter(Movimiento.fecha >= d_start)
        income_unclassified_q = income_unclassified_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        income_classified_q = income_classified_q.filter(Movimiento.fecha <= d_end)
        income_unclassified_q = income_unclassified_q.filter(Movimiento.fecha <= d_end)
    
    # Ejecutar consultas y combinar resultados
    income_classified_data = income_classified_q.group_by(Comercio.id).all()
    income_data = list(income_classified_data)
    
    # Incluir ingresos sin clasificar
    income_unclassified_data = income_unclassified_q.all()
    if income_unclassified_data and income_unclassified_data[0][1] != 0:
        income_data.extend(income_unclassified_data)
    
    income_table = [
        (lbl, abs(total) if total is not None else 0) for lbl, total in income_data
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
        users=users,
        selected_owner=owner_id,
        start_date=start,
        end_date=end,
        selected_cat=cat_id,
        table_limit=table_limit
    )
