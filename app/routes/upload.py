import os
from flask import render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from . import bp
from ..utils.file_loader import register_file, load_movements
from flask_login import login_required, current_user


@bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        tipo_archivo = request.form['tipo_archivo']

        # Validar archivo
        file = request.files.get('file')
        if not file:
            flash('No se seleccionó archivo.', 'danger')
            return redirect(request.url)
        filename = secure_filename(file.filename)
        base_upload = current_app.config['UPLOAD_FOLDER']
        # Guardar en subcarpeta del usuario
        user_folder = os.path.join(base_upload, current_user.username)
        os.makedirs(user_folder, exist_ok=True)
        filepath = os.path.join(user_folder, filename)
        file.save(filepath)

        # Registrar archivo y validar duplicados
        ruta, archivo = register_file(filepath, tipo_archivo, user_id=current_user.id)
        if ruta is None:
            flash('El archivo ya fue cargado previamente.', 'warning')
            return redirect(url_for('main.index'))

        # Procesar movimientos
        count = load_movements(ruta, archivo, tipo_archivo)
        flash(f'Se cargaron {count} movimientos.', 'success')
        return redirect(url_for('main.index'))

    return render_template('upload.html')
