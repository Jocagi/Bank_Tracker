from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from . import bp
from .. import db
from ..models import Movimiento, Pais, CodigoPais
from .comercios import _delete_logo, _save_logo


@bp.route('/paises')
@login_required
def list_paises():
    nombre = request.args.get('q_name', '').strip()
    codigo_iso = request.args.get('q_code', '').strip().upper()
    query = Pais.query
    if nombre:
        query = query.filter(Pais.nombre.ilike(f'%{nombre}%'))
    if codigo_iso:
        query = query.filter(Pais.codigo_iso.ilike(f'%{codigo_iso}%'))
    paises = query.order_by(Pais.nombre).all()
    return render_template(
        'paises.html',
        paises=paises,
        filters={'q_name': nombre, 'q_code': codigo_iso},
    )


@bp.route('/paises/codigos', methods=['GET', 'POST'])
@login_required
def list_codigos_pais():
    codigos = CodigoPais.query.order_by(CodigoPais.digitos, CodigoPais.codigo).all()
    if request.method == 'POST':
        for codigo_pais in codigos:
            activo = request.form.get(f'activo_{codigo_pais.id}') == '1'
            codigo_pais.activo = activo
        db.session.commit()
        flash('Códigos de clasificación actualizados correctamente.', 'success')
        return redirect(url_for('main.list_codigos_pais'))
    return render_template(
        'paises_codigos.html',
        codigos=codigos,
        paises=Pais.query.order_by(Pais.nombre).all(),
    )


@bp.route('/paises/add', methods=['GET', 'POST'])
@login_required
def add_pais():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        codigo_iso = request.form.get('codigo_iso', '').strip().upper()
        if not nombre or not codigo_iso:
            flash('El nombre y el código ISO son obligatorios.', 'warning')
        elif len(codigo_iso) != 2 or not codigo_iso.isalpha():
            flash('El código ISO debe contener exactamente 2 letras.', 'warning')
        elif Pais.query.filter_by(nombre=nombre).first() or Pais.query.filter_by(codigo_iso=codigo_iso).first():
            flash('Ya existe un país con ese nombre o código ISO.', 'warning')
        else:
            try:
                logo_filename = _save_logo(
                    request.files.get('logo'),
                    request.form.get('logo_url') or None,
                    'paises'
                )
            except ValueError as error:
                flash(str(error), 'danger')
                return render_template('paises_add.html')
            except Exception:
                flash('No fue posible descargar la bandera seleccionada.', 'danger')
                return render_template('paises_add.html')
            db.session.add(Pais(nombre=nombre, codigo_iso=codigo_iso, logo_filename=logo_filename))
            db.session.commit()
            flash('País agregado correctamente.', 'success')
            return redirect(url_for('main.list_paises'))
    return render_template('paises_add.html')


@bp.route('/paises/<int:pais_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_pais(pais_id):
    pais = Pais.query.get_or_404(pais_id)
    if request.method == 'POST':
        previous_logo = pais.logo_filename
        nombre = request.form.get('nombre', '').strip()
        codigo_iso = request.form.get('codigo_iso', '').strip().upper()
        duplicate = Pais.query.filter(
            or_(Pais.nombre == nombre, Pais.codigo_iso == codigo_iso),
            Pais.id != pais.id,
        ).first()
        if not nombre or not codigo_iso:
            flash('El nombre y el código ISO son obligatorios.', 'warning')
        elif len(codigo_iso) != 2 or not codigo_iso.isalpha():
            flash('El código ISO debe contener exactamente 2 letras.', 'warning')
        elif duplicate:
            flash('Ya existe otro país con ese nombre o código ISO.', 'warning')
        else:
            try:
                new_logo = _save_logo(
                    request.files.get('logo'),
                    request.form.get('logo_url') or None,
                    'paises'
                )
            except ValueError as error:
                flash(str(error), 'danger')
                return render_template('paises_edit.html', pais=pais)
            except Exception:
                flash('No fue posible descargar la bandera seleccionada.', 'danger')
                return render_template('paises_edit.html', pais=pais)
            pais.nombre = nombre
            pais.codigo_iso = codigo_iso
            if new_logo:
                pais.logo_filename = new_logo
            elif request.form.get('remove_logo') == '1':
                pais.logo_filename = None
            db.session.commit()
            if previous_logo and pais.logo_filename != previous_logo:
                _delete_logo(previous_logo)
            flash('País actualizado correctamente.', 'success')
            return redirect(url_for('main.list_paises'))
    return render_template('paises_edit.html', pais=pais)


@bp.route('/paises/<int:pais_id>/delete', methods=['POST'])
@login_required
def delete_pais(pais_id):
    pais = Pais.query.get_or_404(pais_id)
    movimientos_count = Movimiento.query.filter_by(pais_id=pais.id).count()
    if movimientos_count:
        flash('No se puede eliminar un país que tiene movimientos asociados.', 'warning')
        return redirect(url_for('main.list_paises'))
    logo_filename = pais.logo_filename
    db.session.delete(pais)
    db.session.commit()
    _delete_logo(logo_filename)
    flash('País eliminado.', 'warning')
    return redirect(url_for('main.list_paises'))
