from datetime import datetime
from flask import render_template, request, flash, redirect, url_for
from . import bp
from ..models import Archivo, Movimiento
from .. import db


@bp.route('/archivos', methods=['GET'])
def list_archivos():
    tipo       = request.args.get('tipo_archivo', '')
    start      = request.args.get('start_date', '')
    end        = request.args.get('end_date', '')
    filename_q = request.args.get('filename', '')

    # Consulta base
    query = Archivo.query

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

    archivos = (query
                .order_by(Archivo.upload_date.desc())
                .all())

    # Para el dropdown de tipos
    tipos = [t[0] for t in db.session.query(Archivo.tipo_archivo).distinct().all()]

    return render_template(
        'archivos.html',
        archivos=archivos,
        tipos=tipos,
        type_selected=tipo,
        start_date=start,
        end_date=end,
        filename_query=filename_q
    )


# Eliminar archivo y sus movimientos
@bp.route('/archivos/<int:archivo_id>/delete', methods=['POST'])
def delete_archivo(archivo_id):
    archivo = Archivo.query.get_or_404(archivo_id)
    # Borra movimientos asociados
    Movimiento.query.filter_by(archivo_id=archivo.id).delete()
    # Borra el registro de archivo
    db.session.delete(archivo)
    db.session.commit()
    flash('Archivo y movimientos asociados eliminados.', 'warning')
    return redirect(url_for('main.list_archivos'))
