from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from flask import render_template, request, flash
from sqlalchemy import func
from .. import db
from ..models import Comercio, Categoria, Movimiento, TipoCambio, User, Cuenta
from . import bp
from flask_login import login_required, current_user


@bp.route('/dashboard')
@login_required
def dashboard():
    # ————————————————————————————————————————
    # 1) Leer filtros desde la query string
    # Obtener valores de los filtros directamente
    start = request.args.get('start_date', '')
    end = request.args.get('end_date', '')
    cat_id = request.args.get('category_id', '')
    owner_id = request.args.get('owner_id', '')
    table_limit = request.args.get('table_limit', '10')  # Valor por defecto: 10
    
    # Verificar si hay filtros de fechas o categoría aplicados
    has_date_filters = bool(start or end)
    has_category_filter = bool(cat_id)
    has_owner_filter = bool(owner_id)
    
    # Establecer fechas por defecto solo si no hay filtros de fecha aplicados
    if not has_date_filters and not has_category_filter and not has_owner_filter:
        today = date.today()
        default_start = today - relativedelta(years=2)
        start = default_start.strftime('%Y-%m-%d')
        end = today.strftime('%Y-%m-%d')

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
        try:
            cat_id_int = int(cat_id)
            commerce_classified_q = commerce_classified_q.filter(Comercio.categoria_id == cat_id_int)
            # Para no clasificados, si hay filtro de categoría, no incluirlos
            commerce_unclassified_q = None
        except ValueError:
            pass

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
        try:
            cat_id_int = int(cat_id)
            cat_classified_q = cat_classified_q.filter(Categoria.id == cat_id_int)
            # Para no clasificados, si hay filtro de categoría, no incluirlos
            cat_unclassified_q = None
        except ValueError:
            pass

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
        try:
            cat_id_int = int(cat_id)
            month_classified_q = month_classified_q.filter(Comercio.categoria_id == cat_id_int)
            # Para no clasificados, si hay filtro de categoría, no incluirlos
            month_unclassified_q = None
        except ValueError:
            pass

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
        try:
            cat_id_int = int(cat_id)
            # If category is selected, restrict by comercio's category (same as gastos)
            income_month_classified_q = income_month_classified_q.filter(Comercio.categoria_id == cat_id_int)
            # Para no clasificados, si hay filtro de categoría, no incluirlos
            income_month_unclassified_q = None
        except ValueError:
            pass

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
    # 7) Top 10 Gastos Individuales - Solo movimientos clasificados como gastos
    top_gastos_q = (
        db.session.query(
            Movimiento.descripcion,
            (Movimiento.monto * TipoCambio.valor).label('monto_gtq'),
            Movimiento.fecha,
            Comercio.nombre
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .filter(Movimiento.monto < 0)  # Solo gastos (negativos)
    )
    
    # Aplicar filtros de usuario
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                top_gastos_q = top_gastos_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        top_gastos_q = top_gastos_q.filter(Movimiento.user_id == current_user.id)
    
    # Aplicar filtros de fecha
    if d_start:
        top_gastos_q = top_gastos_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        top_gastos_q = top_gastos_q.filter(Movimiento.fecha <= d_end)
    
    # Aplicar filtro de categoría
    if cat_id:
        try:
            cat_id_int = int(cat_id)
            top_gastos_q = top_gastos_q.filter(Comercio.categoria_id == cat_id_int)
        except ValueError:
            pass
    
    # Ejecutar consulta y obtener top 10
    top_gastos_data = top_gastos_q.order_by((Movimiento.monto * TipoCambio.valor).asc()).limit(10).all()
    
    # Preparar datos para la gráfica
    if top_gastos_data:
        top_gastos_labels = [f"{row[0][:30]}..." if len(row[0]) > 30 else row[0] for row in top_gastos_data]
        top_gastos_values = [abs(row[1]) for row in top_gastos_data]
    else:
        top_gastos_labels = top_gastos_values = []
    
    # ————————————————————————————————————————
    # 8) Gastos por Día de la Semana - Solo movimientos clasificados como gastos
    # Usar función SQL para extraer día de semana (0=domingo, 1=lunes, ..., 6=sábado)
    dia_semana = func.strftime('%w', Movimiento.fecha).label('dia_semana')
    
    gastos_dia_q = (
        db.session.query(
            dia_semana,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .filter(Movimiento.monto < 0)  # Solo gastos (negativos)
    )
    
    # Aplicar filtros de usuario
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                gastos_dia_q = gastos_dia_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        gastos_dia_q = gastos_dia_q.filter(Movimiento.user_id == current_user.id)
    
    # Aplicar filtros de fecha
    if d_start:
        gastos_dia_q = gastos_dia_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        gastos_dia_q = gastos_dia_q.filter(Movimiento.fecha <= d_end)
    
    # Aplicar filtro de categoría
    if cat_id:
        try:
            cat_id_int = int(cat_id)
            gastos_dia_q = gastos_dia_q.filter(Comercio.categoria_id == cat_id_int)
        except ValueError:
            pass
    
    # Ejecutar consulta
    gastos_dia_data = gastos_dia_q.group_by(dia_semana).all()
    
    # Crear diccionario con días de la semana
    dias_nombres = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
    gastos_por_dia = {str(i): 0 for i in range(7)}
    
    for dia, total in gastos_dia_data:
        gastos_por_dia[dia] = abs(total) if total else 0
    
    # Convertir a listas para la gráfica
    weekday_labels = dias_nombres
    weekday_values = [gastos_por_dia[str(i)] for i in range(7)]

    # ————————————————————————————————————————
    # 9) Distribución de Gastos por Rangos
    rangos_gastos_q = (
        db.session.query(
            (Movimiento.monto * TipoCambio.valor).label('monto_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .filter(Movimiento.monto < 0)  # Solo gastos (negativos)
    )
    
    # Aplicar filtros de usuario
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                rangos_gastos_q = rangos_gastos_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        rangos_gastos_q = rangos_gastos_q.filter(Movimiento.user_id == current_user.id)
    
    # Aplicar filtros de fecha y categoría
    if d_start:
        rangos_gastos_q = rangos_gastos_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        rangos_gastos_q = rangos_gastos_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        try:
            cat_id_int = int(cat_id)
            rangos_gastos_q = rangos_gastos_q.filter(Comercio.categoria_id == cat_id_int)
        except ValueError:
            pass
    
    # Obtener todos los gastos
    rangos_data = rangos_gastos_q.all()
    
    # Definir rangos y contar
    rangos = [
        ("Q0-100", 0, 100),
        ("Q100-500", 100, 500), 
        ("Q500-1000", 500, 1000),
        ("Q1000-2000", 1000, 2000),
        ("Q2000+", 2000, float('inf'))
    ]
    
    rangos_count = [0] * len(rangos)
    
    for row in rangos_data:
        monto_abs = abs(row[0]) if row[0] else 0
        for i, (label, min_val, max_val) in enumerate(rangos):
            if min_val <= monto_abs < max_val:
                rangos_count[i] += 1
                break
    
    rangos_labels = [r[0] for r in rangos]
    rangos_values = rangos_count

    # ————————————————————————————————————————
    # 10) Heatmap Calendario de Gastos (último año completo)
    from datetime import timedelta
    
    # Calcular rango de fechas para heatmap (últimos 365 días)
    hoy = date.today()
    hace_365_dias = hoy - timedelta(days=365)
    
    heatmap_gastos_q = (
        db.session.query(
            Movimiento.fecha,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_dia')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .filter(Movimiento.monto < 0)
        .filter(Movimiento.fecha >= hace_365_dias)
        .filter(Movimiento.fecha <= hoy)
    )
    
    # Aplicar filtros de usuario
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                heatmap_gastos_q = heatmap_gastos_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        heatmap_gastos_q = heatmap_gastos_q.filter(Movimiento.user_id == current_user.id)
    
    # Aplicar filtro de categoría
    if cat_id:
        try:
            cat_id_int = int(cat_id)
            heatmap_gastos_q = heatmap_gastos_q.filter(Comercio.categoria_id == cat_id_int)
        except ValueError:
            pass
    
    heatmap_data = heatmap_gastos_q.group_by(Movimiento.fecha).all()
    
    # Crear diccionario de gastos por día
    gastos_por_dia_dict = {}
    for fecha, total in heatmap_data:
        gastos_por_dia_dict[fecha.strftime('%Y-%m-%d')] = abs(total) if total else 0
    
    # Crear lista de todos los días en el rango
    heatmap_dates = []
    heatmap_amounts = []
    current_date = hace_365_dias
    
    while current_date <= hoy:
        date_str = current_date.strftime('%Y-%m-%d')
        heatmap_dates.append(date_str)
        heatmap_amounts.append(gastos_por_dia_dict.get(date_str, 0))
        current_date += timedelta(days=1)

    # ————————————————————————————————————————
    # 11) Gastos Recurrentes vs Únicos (por descripción similar)
    from collections import Counter
    
    recurrentes_q = (
        db.session.query(
            Movimiento.descripcion,
            func.count(Movimiento.id).label('frecuencia'),
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .filter(Movimiento.monto < 0)
    )
    
    # Aplicar filtros de usuario
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                recurrentes_q = recurrentes_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        recurrentes_q = recurrentes_q.filter(Movimiento.user_id == current_user.id)
    
    # Aplicar filtros de fecha y categoría
    if d_start:
        recurrentes_q = recurrentes_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        recurrentes_q = recurrentes_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        try:
            cat_id_int = int(cat_id)
            recurrentes_q = recurrentes_q.filter(Comercio.categoria_id == cat_id_int)
        except ValueError:
            pass
    
    recurrentes_data = recurrentes_q.group_by(Movimiento.descripcion).all()
    
    # Clasificar en recurrentes (>= 2 veces) vs únicos (1 vez)
    total_recurrentes = 0
    total_unicos = 0
    
    for desc, freq, total in recurrentes_data:
        monto_abs = abs(total) if total else 0
        if freq >= 2:
            total_recurrentes += monto_abs
        else:
            total_unicos += monto_abs
    
    recurrentes_labels = ['Gastos Recurrentes', 'Gastos Únicos']
    recurrentes_values = [total_recurrentes, total_unicos]

    # ————————————————————————————————————————
    # 12) Análisis por Cuenta/Moneda
    cuentas_q = (
        db.session.query(
            Cuenta.alias.label('alias'),
            func.concat(Cuenta.banco, ' - ', Cuenta.tipo_cuenta).label('cuenta_nombre'),
            Movimiento.moneda,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .join(Cuenta, Movimiento.cuenta_id == Cuenta.id)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .filter(Movimiento.monto < 0)
    )
    
    # Aplicar filtros de usuario
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                cuentas_q = cuentas_q.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        cuentas_q = cuentas_q.filter(Movimiento.user_id == current_user.id)
    
    # Aplicar filtros de fecha y categoría
    if d_start:
        cuentas_q = cuentas_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        cuentas_q = cuentas_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        try:
            cat_id_int = int(cat_id)
            cuentas_q = cuentas_q.filter(Comercio.categoria_id == cat_id_int)
        except ValueError:
            pass
    
    cuentas_data = cuentas_q.group_by(Cuenta.alias, func.concat(Cuenta.banco, ' - ', Cuenta.tipo_cuenta), Movimiento.moneda).all()
    
    # Preparar datos para gráficas
    cuentas_labels = []
    cuentas_values = []
    monedas_labels = []
    monedas_values = []
    
    # Agrupar por cuenta
    cuentas_dict = {}
    monedas_dict = {}
    
    for alias, cuenta_nombre, moneda, total in cuentas_data:
        monto_abs = abs(total) if total else 0
        
        # Preferir alias si está disponible, si no usar la combinación banco - tipo
        cuenta_key = alias if alias else (cuenta_nombre or 'Sin cuenta')
        cuentas_dict[cuenta_key] = cuentas_dict.get(cuenta_key, 0) + monto_abs
        
        # Por moneda
        monedas_dict[moneda] = monedas_dict.get(moneda, 0) + monto_abs
    
    # Convertir a listas
    cuentas_labels = list(cuentas_dict.keys())
    cuentas_values = list(cuentas_dict.values())
    monedas_labels = list(monedas_dict.keys())
    monedas_values = list(monedas_dict.values())

    # ————————————————————————————————————————
    # COMERCIOS MÁS RECURRENTES
    # ————————————————————————————————————————
    # Query para contar transacciones por comercio (solo gastos clasificados)
    comercios_recurrentes_query = db.session.query(
        Comercio.nombre,
        func.count(Movimiento.id).label('count')
    ).join(
        Movimiento, Movimiento.comercio_id == Comercio.id
    ).join(
        Categoria, Comercio.categoria_id == Categoria.id
    ).filter(
        Comercio.tipo_contabilizacion == 'gastos'  # Solo gastos
    )
    
    # Aplicar filtros de usuario
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        if owner_id:
            try:
                oid = int(owner_id)
                comercios_recurrentes_query = comercios_recurrentes_query.filter(Movimiento.user_id == oid)
            except ValueError:
                pass
    else:
        comercios_recurrentes_query = comercios_recurrentes_query.filter(Movimiento.user_id == current_user.id)

    # Aplicar filtros de fecha
    if d_start:
        comercios_recurrentes_query = comercios_recurrentes_query.filter(Movimiento.fecha >= d_start)
    if d_end:
        comercios_recurrentes_query = comercios_recurrentes_query.filter(Movimiento.fecha <= d_end)
    
    # Filtro de categoría
    if cat_id:
        try:
            cat_id_int = int(cat_id)
            comercios_recurrentes_query = comercios_recurrentes_query.filter(Comercio.categoria_id == cat_id_int)
        except ValueError:
            pass

    # Agrupar, ordenar y limitar a top 10
    comercios_recurrentes_result = comercios_recurrentes_query.group_by(
        Comercio.nombre
    ).order_by(
        func.count(Movimiento.id).desc()
    ).limit(10).all()

    comercios_recurrentes_labels = [c.nombre for c in comercios_recurrentes_result]
    comercios_recurrentes_values = [c.count for c in comercios_recurrentes_result]

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
        # Nuevas gráficas
        top_gastos_labels=top_gastos_labels,
        top_gastos_values=top_gastos_values,
        weekday_labels=weekday_labels,
        weekday_values=weekday_values,
        # Gráficas adicionales
        rangos_labels=rangos_labels,
        rangos_values=rangos_values,
        heatmap_dates=heatmap_dates,
        heatmap_amounts=heatmap_amounts,
        recurrentes_labels=recurrentes_labels,
        recurrentes_values=recurrentes_values,
        cuentas_labels=cuentas_labels,
        cuentas_values=cuentas_values,
        monedas_labels=monedas_labels,
        monedas_values=monedas_values,
        comercios_recurrentes_labels=comercios_recurrentes_labels,
        comercios_recurrentes_values=comercios_recurrentes_values,
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
