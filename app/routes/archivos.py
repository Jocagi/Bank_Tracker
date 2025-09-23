from datetime import datetime
from flask import render_template, request, flash, redirect, url_for
from . import bp
from ..models import Archivo, Movimiento
from .. import db
from flask_login import login_required, current_user
from ..models import User


@bp.route('/archivos', methods=['GET'])
@login_required
def list_archivos():
    tipo       = request.args.get('tipo_archivo', '')
    start      = request.args.get('start_date', '')
    end        = request.args.get('end_date', '')
    filename_q = request.args.get('filename', '')

    # Consulta base
    query = Archivo.query
    # Owner filter (admins can filter by owner_id)
    selected_owner = request.args.get('owner_id', '')
    if selected_owner and (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        try:
            oid = int(selected_owner)
            query = query.filter(Archivo.user_id == oid)
        except ValueError:
            flash('Owner inválido', 'warning')
    # Los usuarios normales solo ven sus archivos
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        query = query.filter(Archivo.user_id == current_user.id)

    if tipo:
        query = query.filter(Archivo.tipo_archivo == tipo)
    if start:
        try:
            d1 = datetime.strptime(start, '%Y-%m-%d')
            query = query.filter(Archivo.upload_date >= d1)
        except ValueError:
            flash('Fecha “Desde” inválida', 'warning')
    if end:
        try:
            d2 = datetime.strptime(end, '%Y-%m-%d')
            query = query.filter(Archivo.upload_date <= d2)
        except ValueError:
            flash('Fecha “Hasta” inválida', 'warning')
    if filename_q:
        query = query.filter(Archivo.filename.ilike(f'%{filename_q}%'))

    # Apply ordering and fetch
    archivos = (query
                .order_by(Archivo.upload_date.desc())
                .all())

    users = []
    if hasattr(current_user, 'is_admin') and current_user.is_admin():
        users = User.query.order_by(User.username).all()

    # Para el dropdown de tipos
    tipos = [t[0] for t in db.session.query(Archivo.tipo_archivo).distinct().all()]

    return render_template(
        'archivos.html',
        archivos=archivos,
        tipos=tipos,
        type_selected=tipo,
        start_date=start,
        end_date=end,
        filename_query=filename_q,
        users=users,
        selected_owner=selected_owner
    )


# Eliminar archivo y sus movimientos
@bp.route('/archivos/<int:archivo_id>/delete', methods=['POST'])
@login_required
def delete_archivo(archivo_id):
    archivo = Archivo.query.get_or_404(archivo_id)
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        if archivo.user_id != current_user.id:
            flash('Acceso denegado', 'danger')
            return redirect(url_for('main.list_archivos'))
    # Borra movimientos asociados
    Movimiento.query.filter_by(archivo_id=archivo.id).delete()
    # Borra el registro de archivo
    db.session.delete(archivo)
    db.session.commit()
    flash('Archivo y movimientos asociados eliminados.', 'warning')
    return redirect(url_for('main.list_archivos'))



@bp.route('/archivos/<int:archivo_id>/movimientos', methods=['GET'])
@login_required
def archivos_movimientos(archivo_id):
    archivo = Archivo.query.get_or_404(archivo_id)
    if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
        if archivo.user_id != current_user.id:
            flash('Acceso denegado', 'danger')
            return redirect(url_for('main.list_archivos'))
    movimientos = Movimiento.query.filter_by(archivo_id=archivo.id).order_by(Movimiento.fecha.desc()).all()
    return render_template('archivos_movimientos.html', archivo=archivo, movimientos=movimientos)
