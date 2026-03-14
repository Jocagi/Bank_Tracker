from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from . import bp
from ..models import Movimiento, Comercio, Regla, User, Factura
from ..utils.classifier import reclasificar_movimientos
from .. import db


@bp.route('/sin_clasificar', methods=['GET'])
@login_required
def sin_clasificar():
    # Obtener filtro de usuario seleccionado (solo para admins)
    selected_owner = request.args.get('owner_id', '')

    # Parámetros de recomendación de factura
    # Defaults: +-7 días, 0.01% y Q0.01 de tolerancia
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

    # Recomendación de factura por movimiento:
    # misma persona dueña del movimiento, fecha dentro de +-N días,
    # y monto similar usando tolerancia combinada absoluta/porcentual.
    recomendaciones_factura = {}
    if movimientos:
        fechas = [m.fecha for m in movimientos if m.fecha is not None]
        if fechas:
            min_fecha = min(fechas)
            max_fecha = max(fechas)

            facturas_query = Factura.query.filter(
                Factura.fecha_emision >= min_fecha,
                Factura.fecha_emision <= max_fecha
            )

            # Extender ventana para poder evaluar +-N días por movimiento.
            from datetime import timedelta
            facturas_query = facturas_query.filter(
                Factura.fecha_emision >= (min_fecha - timedelta(days=days_window_int)),
                Factura.fecha_emision <= (max_fecha + timedelta(days=days_window_int))
            )

            # Respetar owner seleccionado cuando aplique.
            if hasattr(current_user, 'is_admin') and current_user.is_admin():
                if selected_owner:
                    try:
                        oid = int(selected_owner)
                        facturas_query = facturas_query.filter(Factura.user_id == oid)
                    except ValueError:
                        pass
            else:
                facturas_query = facturas_query.filter(Factura.user_id == current_user.id)

            facturas = facturas_query.all()

            # Agrupar facturas por usuario para evitar cruces entre usuarios.
            facturas_por_user = {}
            for f in facturas:
                facturas_por_user.setdefault(f.user_id, []).append(f)

            for m in movimientos:
                if m.fecha is None or m.monto is None:
                    continue

                monto_mov = abs(float(m.monto))
                if monto_mov == 0:
                    continue

                candidatas = facturas_por_user.get(m.user_id, [])
                matches = []

                for f in candidatas:
                    if f.fecha_emision is None or f.gran_total is None:
                        continue

                    diff_dias = abs((f.fecha_emision.date() - m.fecha).days)
                    if diff_dias > days_window_int:
                        continue

                    monto_factura = abs(float(f.gran_total))
                    diff_monto = abs(monto_mov - monto_factura)
                    pct_diff = diff_monto / monto_mov

                    # Tolerancia flexible para capturar "monto similar".
                    # Acepta si difiere <= pct_tolerance o <= abs_tolerance.
                    if pct_diff > pct_tolerance_float and diff_monto > abs_tolerance_float:
                        continue

                    # Priorizamos menor diferencia porcentual, luego monto y luego cercanía de fecha.
                    score = (pct_diff, diff_monto, diff_dias)
                    matches.append({
                        'factura': f,
                        'diff_monto': diff_monto,
                        'pct_diff': pct_diff,
                        'diff_dias': diff_dias,
                        'score': score,
                    })

                if matches:
                    matches.sort(key=lambda x: x['score'])
                    recomendaciones_factura[m.id] = matches[:3]
    
    return render_template('sin_clasificar.html',
                           movimientos=movimientos,
                           comercios=comercios,
                           recomendaciones_factura=recomendaciones_factura,
                           fact_days=days_window_int,
                           fact_pct=(pct_tolerance_float * 100.0),
                           fact_abs=abs_tolerance_float,
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



