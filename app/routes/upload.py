import os
from flask import render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from . import bp
from ..utils.file_loader import register_file, load_movements


@bp.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        tipo_archivo = request.form['tipo_archivo']

        # Validar archivo
        file = request.files.get('file')
        if not file:
            flash('No se seleccionó archivo.', 'danger')
            return redirect(request.url)
        filename = secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)

        # Registrar archivo y validar duplicados
        ruta, archivo = register_file(filepath, tipo_archivo)
        if ruta is None:
            flash('El archivo ya fue cargado previamente.', 'warning')
            return redirect(url_for('main.index'))

        # Procesar movimientos
        count = load_movements(ruta, archivo, tipo_archivo)
        flash(f'Se cargaron {count} movimientos.', 'success')
        return redirect(url_for('main.index'))

    return render_template('upload.html')
