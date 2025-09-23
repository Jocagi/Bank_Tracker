import os
from datetime import datetime
from flask import render_template, request, flash
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from .. import db
from ..models import Movimiento, Cuenta, Comercio, Categoria, TipoCambio
from ..models import Movimiento as MovimientoModel
from . import bp


@bp.route('/')
def index():
    # Lectura de filtros desde query string
    start               = request.args.get('start_date', '')
    end                 = request.args.get('end_date', '')
    desc                = request.args.get('desc', '')
    selected_cuenta     = request.args.get('cuenta_id', '')
    selected_comercio   = request.args.get('comercio_id', '')
    selected_categoria  = request.args.get('categoria_id', '')
    selected_tipo_cont  = request.args.get('tipo_contabilizacion', '')

    # Base de la consulta con eager loading
    query = Movimiento.query.options(
        joinedload(Movimiento.comercio)
                   .joinedload(Comercio.categoria),
        joinedload(Movimiento.cuenta)
    )

    # Filtros existentes...
    if start:
        try:
            d1 = datetime.strptime(start, '%Y-%m-%d').date()
            query = query.filter(Movimiento.fecha >= d1)
        except ValueError:
            flash('Fecha “Desde” inválida', 'warning')
    if end:
        try:
            d2 = datetime.strptime(end, '%Y-%m-%d').date()
            query = query.filter(Movimiento.fecha <= d2)
        except ValueError:
            flash('Fecha “Hasta” inválida', 'warning')
    if desc:
        query = query.filter(Movimiento.descripcion.ilike(f'%{desc}%'))
    if selected_comercio:
        query = query.filter(Movimiento.comercio_id == int(selected_comercio))
    if selected_categoria:
        query = query.filter(
            Movimiento.comercio.has(categoria_id=int(selected_categoria))
        )
    if selected_tipo_cont:
        query = query.filter(
            Movimiento.comercio.has(tipo_contabilizacion=selected_tipo_cont)
        )

    # --- Nuevo filtro por Cuenta ---
    if selected_cuenta:
        query = query.filter(Movimiento.cuenta_id == int(selected_cuenta))

    # Obtener los movimientos
    movimientos = (
        query.order_by(Movimiento.fecha.desc())
             .limit(100)
             .all()
    )

    # Totales
    total_movs  = len(movimientos)
    sum_debito  = sum(m.monto for m in movimientos if m.tipo == 'debito')
    sum_credito = sum(m.monto for m in movimientos if m.tipo == 'credito')

    # Opciones para los selects
    cuentas     = Cuenta.query.order_by(Cuenta.numero_cuenta).all()
    comercios   = Comercio.query.order_by(Comercio.nombre).all()
    categorias  = Categoria.query.order_by(Categoria.nombre).all()
    tipos       = ['ingresos', 'gastos', 'transferencias']

    return render_template(
        'index.html',
        movimientos=movimientos,
        total_movs=total_movs,
        sum_debito=sum_debito,
        sum_credito=sum_credito,
        # valores actuales de los filtros
        start_date=start,
        end_date=end,
        desc_query=desc,
        selected_cuenta=selected_cuenta,
        selected_comercio=selected_comercio,
        selected_categoria=selected_categoria,
        selected_tipo_cont=selected_tipo_cont,
        # listas para los selects
        cuentas=cuentas,
        comercios=comercios,
        categorias=categorias,
        tipos_contabilizacion=tipos
    )

