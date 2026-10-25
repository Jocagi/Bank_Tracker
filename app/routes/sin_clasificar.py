from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from . import bp
from ..models import Movimiento, Comercio, Regla, ReglaCondicion, User, Factura, Categoria, Subcategoria
from ..utils.classifier import reclasificar_movimientos, reclasificar_comercio, describir_regla
from .. import db
from sqlalchemy.orm import joinedload


def _crear_regla_automatica_desde_movimiento(comercio_id, movimiento):
    """
    Crea una regla "incluir" con una única condición de igualdad exacta
    (case-insensitive) sobre la descripción del movimiento, igual que el
    comportamiento histórico de asignación rápida desde "Sin clasificar".
    El nombre de la regla se deriva de la condición, no se pide al usuario.
    """
    regla = Regla(comercio_id=comercio_id, tipo='incluir')
    regla.condiciones.append(ReglaCondicion(
        orden=0,
        conector='AND',
        negar=False,
        campo='descripcion',
        operador='igual',
        valor=movimiento.descripcion,
    ))
    regla.descripcion = describir_regla(regla)[:200]
    db.session.add(regla)
    return regla


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
    categorias = Categoria.query.order_by(Categoria.nombre).all()
    subcategorias = Subcategoria.query.options(joinedload(Subcategoria.categoria)).order_by(Subcategoria.nombre).all()

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
                           categorias=categorias,
                           subcategorias=subcategorias,
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

    # Crear regla "incluir" con una condición exacta sobre la descripción
    _crear_regla_automatica_desde_movimiento(comercio.id, movimiento)
    db.session.commit()

    # Solo se reevalúan los movimientos afectados por las reglas del comercio
    cambios = reclasificar_comercio(comercio.id)

    flash(f'Se ha añadido la regla. Movimientos reclasificados: {cambios}.', 'success')
    return redirect(url_for('main.edit_comercio', comercio_id=comercio.id))


@bp.route('/sin_clasificar/quick-create-comercio', methods=['POST'])
@login_required
def quick_create_comercio():
    mov_id = request.form.get('movimiento_id')
    movimiento = Movimiento.query.get_or_404(mov_id)

    nombre = request.form.get('nombre', '').strip()
    categoria_id = request.form.get('categoria_id', type=int)
    subcategoria_id_raw = request.form.get('subcategoria_id') or ''
    subcategoria_id = int(subcategoria_id_raw) if subcategoria_id_raw else None
    tipo_contabilizacion = request.form.get('tipo_contabilizacion') or 'gastos'

    if not nombre or not categoria_id:
        flash('El nombre y la categoría son obligatorios para crear el comercio.', 'danger')
        return redirect(url_for('main.sin_clasificar'))

    if subcategoria_id is not None:
        subcategoria = Subcategoria.query.get_or_404(subcategoria_id)
        if subcategoria.categoria_id != categoria_id:
            flash('La subcategoría debe pertenecer a la categoría seleccionada.', 'danger')
            return redirect(url_for('main.sin_clasificar'))

    comercio = Comercio(
        nombre=nombre,
        categoria_id=categoria_id,
        subcategoria_id=subcategoria_id,
        tipo_contabilizacion=tipo_contabilizacion,
    )
    db.session.add(comercio)
    db.session.flush()

    # Crear regla "incluir" con una condición exacta sobre la descripción,
    # igual que al asignar un comercio existente.
    _crear_regla_automatica_desde_movimiento(comercio.id, movimiento)
    db.session.commit()

    cambios = reclasificar_comercio(comercio.id)

    flash(f'Comercio creado. Movimientos reclasificados: {cambios}.', 'success')
    return redirect(url_for('main.edit_comercio', comercio_id=comercio.id))


@bp.route('/sin_clasificar/reclasificar-todo', methods=['POST'])
@login_required
def reclasificar_todo():
    """Reclasificación completa bajo demanda (operación costosa)."""
    cambios = reclasificar_movimientos()
    flash(f'Reclasificación completa finalizada. Movimientos que cambiaron de comercio: {cambios}.', 'success')
    return redirect(url_for('main.sin_clasificar'))


@bp.route('/movimiento/<int:mov_id>/asignar', methods=['POST'])
def asignar_movimiento(mov_id):
    mov = Movimiento.query.get_or_404(mov_id)
    comercio_id = request.form.get('comercio_id')
    mov.comercio_id = comercio_id
    db.session.commit()
    flash('Movimiento clasificado manualmente.', 'success')
    return redirect(url_for('main.sin_clasificar'))



