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

        # Validar archivos (ahora múltiples)
        files = request.files.getlist('files')
        if not files or all(not f.filename for f in files):
            flash('No se seleccionaron archivos.', 'danger')
            return redirect(request.url)

        base_upload = current_app.config['UPLOAD_FOLDER']
        # Guardar en subcarpeta del usuario
        user_folder = os.path.join(base_upload, current_user.username)
        os.makedirs(user_folder, exist_ok=True)

        total_movements = 0
        processed_files = 0
        duplicate_files = 0
        error_files = []

        # Procesar cada archivo
        for file in files:
            if not file.filename:
                continue
                
            try:
                filename = secure_filename(file.filename)
                filepath = os.path.join(user_folder, filename)
                file.save(filepath)

                # Registrar archivo y validar duplicados
                ruta, archivo = register_file(filepath, tipo_archivo, user_id=current_user.id)
                if ruta is None:
                    duplicate_files += 1
                    # Eliminar archivo duplicado del disco
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    continue

                # Procesar movimientos
                count = load_movements(ruta, archivo, tipo_archivo)
                total_movements += count
                processed_files += 1

            except Exception as e:
                error_files.append(f"{file.filename}: {str(e)}")
                # Limpiar archivo con error si existe
                if 'filepath' in locals() and os.path.exists(filepath):
                    os.remove(filepath)

        # Mostrar resultados
        if processed_files > 0:
            flash(f'Se procesaron {processed_files} archivo(s) con {total_movements} movimientos en total.', 'success')
        
        if duplicate_files > 0:
            flash(f'{duplicate_files} archivo(s) ya habían sido cargados previamente.', 'warning')
            
        if error_files:
            flash(f'Error procesando: {"; ".join(error_files)}', 'danger')

        return redirect(url_for('main.index'))

    return render_template('upload.html')
