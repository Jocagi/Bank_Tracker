from datetime import datetime
from urllib.parse import urlencode
from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_, func

from . import bp
from ..models import Factura, User
from ..utils.sorting import SORT_DESC, resolver_orden, aplicar_orden, construir_enlaces_orden


@bp.route('/facturas', methods=['GET'])
@login_required
def list_facturas():
    tipo = request.args.get('tipo_documento', '')
    start = request.args.get('start_date', '')
    end = request.args.get('end_date', '')
    emisor_q = request.args.get('emisor', '')
    receptor_q = request.args.get('receptor', '')
    uuid_q = request.args.get('uuid', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    if per_page not in (25, 50, 100):
        per_page = 25

    query = Factura.query

    selected_owner = request.args.get('owner_id', '')
    if selected_owner and (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        try:
            oid = int(selected_owner)
            query = query.filter(Factura.user_id == oid)
        except ValueError:
            flash('Owner inválido', 'warning')

    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        query = query.filter(Factura.user_id == current_user.id)

    if tipo:
        query = query.filter(Factura.tipo_documento == tipo)

    if start:
        try:
            d1 = datetime.strptime(start, '%Y-%m-%d')
            query = query.filter(Factura.fecha_emision >= d1)
        except ValueError:
            flash('Fecha "Desde" inválida', 'warning')

    if end:
        try:
            d2 = datetime.strptime(end, '%Y-%m-%d')
            query = query.filter(Factura.fecha_emision <= d2)
        except ValueError:
            flash('Fecha "Hasta" inválida', 'warning')

    if emisor_q:
        query = query.filter(
            or_(
                Factura.emisor_nombre.ilike(f'%{emisor_q}%'),
                Factura.emisor_nombre_comercial.ilike(f'%{emisor_q}%'),
            )
        )

    if receptor_q:
        query = query.filter(Factura.receptor_nombre.ilike(f'%{receptor_q}%'))

    if uuid_q:
        query = query.filter(Factura.uuid.ilike(f'%{uuid_q}%'))

    columnas_orden = {
        'fecha': Factura.fecha_emision,
        'tipo': func.lower(func.coalesce(Factura.tipo_documento, '')),
        'uuid': func.lower(func.coalesce(Factura.uuid, '')),
        'emisor': func.lower(func.coalesce(Factura.emisor_nombre_comercial, Factura.emisor_nombre, '')),
        'receptor': func.lower(func.coalesce(Factura.receptor_nombre, '')),
        'moneda': func.lower(func.coalesce(Factura.moneda, '')),
        'total': func.coalesce(Factura.gran_total, 0),
    }
    sort_key, sort_dir = resolver_orden(columnas_orden, 'fecha', SORT_DESC)
    sort_links = construir_enlaces_orden('main.list_facturas', columnas_orden, sort_key, sort_dir)

    # Orden server-side: aplica a todas las páginas
    pagination = aplicar_orden(query, columnas_orden, sort_key, sort_dir, Factura.id).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    facturas = pagination.items

    users = []
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        users = User.query.order_by(User.username).all()

    tipos_documento = [t[0] for t in Factura.query.with_entities(Factura.tipo_documento).distinct().all() if t[0]]

    query_params = {}
    if tipo:
        query_params['tipo_documento'] = tipo
    if start:
        query_params['start_date'] = start
    if end:
        query_params['end_date'] = end
    if emisor_q:
        query_params['emisor'] = emisor_q
    if receptor_q:
        query_params['receptor'] = receptor_q
    if uuid_q:
        query_params['uuid'] = uuid_q
    if selected_owner:
        query_params['owner_id'] = selected_owner
    query_params['per_page'] = per_page
    query_params['sort'] = sort_key
    query_params['dir'] = sort_dir

    query_string = urlencode(query_params)

    return render_template(
        'facturas.html',
        facturas=facturas,
        pagination=pagination,
        per_page=per_page,
        query_string=query_string,
        sort_key=sort_key,
        sort_dir=sort_dir,
        sort_links=sort_links,
        tipos_documento=tipos_documento,
        type_selected=tipo,
        start_date=start,
        end_date=end,
        emisor_query=emisor_q,
        receptor_query=receptor_q,
        uuid_query=uuid_q,
        users=users,
        selected_owner=selected_owner,
    )


@bp.route('/facturas/<int:factura_id>', methods=['GET'])
@login_required
def factura_detalle(factura_id):
    factura = Factura.query.get_or_404(factura_id)

    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        if factura.user_id != current_user.id:
            flash('Acceso denegado', 'danger')
            return redirect(url_for('main.list_facturas'))

    return render_template('factura_detalle.html', factura=factura)
