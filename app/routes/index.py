import os
import hashlib
from datetime import datetime, timedelta
from flask import render_template, request, flash
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from .. import db
from ..models import Movimiento, Cuenta, Comercio, Categoria, TipoCambio, User, Archivo, Factura
from ..models import Movimiento as MovimientoModel
from . import bp
from flask import redirect, url_for
from flask_login import login_required, current_user


@bp.route('/')
@login_required
def index():
    # Lectura de filtros desde query string
    start               = request.args.get('start_date', '')
    end                 = request.args.get('end_date', '')
    desc                = request.args.get('desc', '')
    selected_cuenta     = request.args.get('cuenta_id', '')
    selected_comercio   = request.args.get('comercio_id', '')
    selected_categoria  = request.args.get('categoria_id', '')
    selected_tipo_cont  = request.args.get('tipo_contabilizacion', '')
    selected_owner = request.args.get('owner_id', '')

    # Base de la consulta
    query = Movimiento.query.options(
        joinedload(Movimiento.comercio)
                   .joinedload(Comercio.categoria),
        joinedload(Movimiento.cuenta)
    )
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
    

    # Filtros
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
    if selected_cuenta:
        query = query.filter(Movimiento.cuenta_id == int(selected_cuenta))

    # Obtener los movimientos
    # Aplicar límite de 100 solo cuando no hay filtros (para la vista por defecto)
    has_filters = any([
        start,
        end,
        desc,
        selected_cuenta,
        selected_comercio,
        selected_categoria,
        selected_tipo_cont,
    ])

    q = query.order_by(Movimiento.fecha.desc())
    if not has_filters:
        q = q.limit(100)

    movimientos = q.all()

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
        , users=users, selected_owner=selected_owner
    )


@bp.route('/movimiento/<int:mov_id>/edit', methods=['GET', 'POST'])
def edit_movimiento(mov_id):
    mov = Movimiento.query.get_or_404(mov_id)
    cuentas   = Cuenta.query.order_by(Cuenta.numero_cuenta).all()
    comercios = Comercio.query.order_by(Comercio.nombre).all()
    
    # Detectar si viene desde sin_clasificar
    from_sin_clasificar = request.args.get('from') == 'sin_clasificar'

    if request.method == 'POST':
        # Obtener valores del formulario
        try:
            mov.fecha = datetime.strptime(request.form.get('fecha'), '%Y-%m-%d').date()
        except Exception:
            flash('Fecha inválida', 'warning')
            return redirect(url_for('main.edit_movimiento', mov_id=mov.id))

        mov.descripcion = request.form.get('descripcion')
        mov.detalle = request.form.get('detalle') or None
        mov.lugar = request.form.get('lugar') or None
        mov.numero_documento = request.form.get('numero_documento') or None
        monto = request.form.get('monto')
        try:
            mov.monto = float(monto) if monto not in (None, '') else None
        except ValueError:
            flash('Monto inválido', 'warning')
            return redirect(url_for('main.edit_movimiento', mov_id=mov.id))

        mov.moneda = request.form.get('moneda') or mov.moneda
        mov.tipo = request.form.get('tipo') or mov.tipo
        cuenta_id = request.form.get('cuenta_id')
        comercio_id = request.form.get('comercio_id')
        # Excluir de clasificación automática: checkbox sends 'on' when checked
        excluir = request.form.get('excluir_clasificacion')
        mov.excluir_clasificacion = True if excluir in ('on', '1', 'true', 'True') else False
        excluir_dashboard = request.form.get('excluir_dashboard')
        mov.excluir_dashboard = True if excluir_dashboard in ('on', '1', 'true', 'True') else False

        if cuenta_id:
            mov.cuenta_id = int(cuenta_id)
        else:
            flash('Debe seleccionar una cuenta', 'warning')
            return redirect(url_for('main.edit_movimiento', mov_id=mov.id))

        mov.comercio_id = int(comercio_id) if comercio_id else None

        # Guardar cambios
        db.session.commit()
        
        # Si viene desde sin_clasificar y se cumplen las condiciones, reclasificar
        if from_sin_clasificar and not mov.excluir_clasificacion and not mov.comercio_id:
            try:
                from ..utils.classifier import reclasificar_movimientos
                reclasificar_movimientos()
                # Recargar el movimiento para ver si fue clasificado
                db.session.refresh(mov)
                if mov.comercio_id:
                    flash('Movimiento actualizado y clasificado automáticamente.', 'success')
                else:
                    flash('Movimiento actualizado. No se pudo clasificar automáticamente.', 'info')
            except Exception as e:
                flash(f'Movimiento actualizado, pero error en reclasificación: {str(e)}', 'warning')
        else:
            flash('Movimiento actualizado.', 'success')
        
        # Redirigir según el origen
        if from_sin_clasificar:
            return redirect(url_for('main.sin_clasificar'))
        else:
            return redirect(url_for('main.index'))

    return render_template('movimiento_edit.html', mov=mov, cuentas=cuentas, comercios=comercios)


def _get_or_create_archivo_manual(user_id):
    """Obtiene o crea el registro Archivo 'manual' para un usuario dado."""
    hash_key = hashlib.sha256(f'manual_{user_id}'.encode()).hexdigest()
    archivo = Archivo.query.filter_by(file_hash=hash_key).first()
    if not archivo:
        archivo = Archivo(
            tipo_archivo='manual',
            filename='manual',
            file_hash=hash_key,
            user_id=user_id,
        )
        db.session.add(archivo)
        db.session.flush()  # obtener el id sin hacer commit completo
    return archivo


@bp.route('/movimiento/nuevo', methods=['GET', 'POST'])
@login_required
def add_movimiento():
    from datetime import date as _date
    cuentas   = Cuenta.query.order_by(Cuenta.numero_cuenta).all()
    comercios = Comercio.query.order_by(Comercio.nombre).all()
    today = _date.today().isoformat()

    if request.method == 'POST':
        # Fecha
        try:
            fecha = datetime.strptime(request.form.get('fecha', ''), '%Y-%m-%d').date()
        except ValueError:
            flash('Fecha inválida.', 'warning')
            return redirect(url_for('main.add_movimiento'))

        descripcion     = request.form.get('descripcion', '').strip()
        detalle         = request.form.get('detalle') or None
        lugar           = request.form.get('lugar') or None
        numero_documento = request.form.get('numero_documento') or None

        monto_raw = request.form.get('monto', '')
        try:
            monto = float(monto_raw) if monto_raw not in (None, '') else None
        except ValueError:
            flash('Monto inválido.', 'warning')
            return redirect(url_for('main.add_movimiento'))

        moneda  = request.form.get('moneda', '').strip() or None
        tipo    = request.form.get('tipo', 'debito')

        cuenta_id = request.form.get('cuenta_id')
        if not cuenta_id:
            flash('Debe seleccionar una cuenta.', 'warning')
            return redirect(url_for('main.add_movimiento'))

        comercio_id = request.form.get('comercio_id') or None
        excluir     = request.form.get('excluir_clasificacion')
        excluir_clasificacion = excluir in ('on', '1', 'true', 'True')
        excluir_db  = request.form.get('excluir_dashboard')
        excluir_dashboard = excluir_db in ('on', '1', 'true', 'True')

        archivo = _get_or_create_archivo_manual(current_user.id)

        mov = Movimiento(
            fecha=fecha,
            descripcion=descripcion,
            detalle=detalle,
            lugar=lugar,
            numero_documento=numero_documento,
            monto=monto,
            moneda=moneda,
            tipo=tipo,
            cuenta_id=int(cuenta_id),
            comercio_id=int(comercio_id) if comercio_id else None,
            excluir_clasificacion=excluir_clasificacion,
            excluir_dashboard=excluir_dashboard,
            archivo_id=archivo.id,
            user_id=current_user.id,
        )
        db.session.add(mov)
        db.session.commit()
        flash('Movimiento creado correctamente.', 'success')
        return redirect(url_for('main.index'))

    return render_template('movimiento_add.html', cuentas=cuentas, comercios=comercios, today=today)


@bp.route('/movimiento/<int:mov_id>/delete', methods=['POST'])
def delete_movimiento(mov_id):
    mov = Movimiento.query.get_or_404(mov_id)
    # intentar obtener url de retorno
    next_url = request.form.get('next') or request.args.get('next')
    db.session.delete(mov)
    db.session.commit()
    flash('Movimiento eliminado.', 'warning')
    if next_url:
        return redirect(next_url)
    return redirect(url_for('main.index'))


@bp.route('/movimiento/<int:mov_id>/facturas-relacionadas', methods=['GET'])
@login_required
def movimiento_facturas_relacionadas(mov_id):
    movimiento = Movimiento.query.get_or_404(mov_id)

    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        if movimiento.user_id != current_user.id:
            flash('Acceso denegado', 'danger')
            return redirect(url_for('main.index'))

    days_window = request.args.get('fact_days', '7')
    pct_tolerance = request.args.get('fact_pct', '0.01')
    abs_tolerance = request.args.get('fact_abs', '0.01')

    try:
        days_window_int = max(0, int(days_window))
    except ValueError:
        days_window_int = 7

    try:
        pct_tolerance_float = max(0.0, float(pct_tolerance)) / 100.0
    except ValueError:
        pct_tolerance_float = 0.0001

    try:
        abs_tolerance_float = max(0.0, float(abs_tolerance))
    except ValueError:
        abs_tolerance_float = 0.01

    matches = []
    if movimiento.fecha is not None and movimiento.monto is not None:
        monto_mov = abs(float(movimiento.monto))
        if monto_mov > 0:
            facturas = Factura.query.filter(
                Factura.user_id == movimiento.user_id,
                Factura.fecha_emision >= (movimiento.fecha - timedelta(days=days_window_int)),
                Factura.fecha_emision <= (movimiento.fecha + timedelta(days=days_window_int)),
            ).all()

            for f in facturas:
                if f.fecha_emision is None or f.gran_total is None:
                    continue

                diff_dias = abs((f.fecha_emision.date() - movimiento.fecha).days)
                if diff_dias > days_window_int:
                    continue

                monto_factura = abs(float(f.gran_total))
                diff_monto = abs(monto_mov - monto_factura)
                pct_diff = diff_monto / monto_mov

                if pct_diff > pct_tolerance_float and diff_monto > abs_tolerance_float:
                    continue

                score = (pct_diff, diff_monto, diff_dias)
                matches.append({
                    'factura': f,
                    'diff_monto': diff_monto,
                    'pct_diff': pct_diff,
                    'diff_dias': diff_dias,
                    'score': score,
                })

            matches.sort(key=lambda x: x['score'])
            matches = matches[:3]

    return render_template(
        'movimiento_facturas_relacionadas.html',
        movimiento=movimiento,
        matches=matches,
        fact_days=days_window_int,
        fact_pct=(pct_tolerance_float * 100.0),
        fact_abs=abs_tolerance_float,
    )

