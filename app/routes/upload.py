import os
import uuid
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from . import bp
from ..utils.file_loader import register_file, register_batch_folder, load_movements, load_facturas
from .. import db
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

        valid_files = [f for f in files if f and f.filename]

        # Para facturas: crear lote (subcarpeta) cuando se cargan varias a la vez.
        # Además usamos un solo registro Archivo para todo el lote en administración.
        batch_folder = None
        batch_archivo = None
        if tipo_archivo == 'factura-fel-xml' and len(valid_files) > 1:
            batch_name = f"lote_facturas_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            batch_folder = os.path.join(user_folder, batch_name)
            os.makedirs(batch_folder, exist_ok=True)
            batch_archivo = register_batch_folder(batch_folder, tipo_archivo, user_id=current_user.id)

        total_movements = 0
        total_facturas = 0
        total_detalles_factura = 0
        duplicate_facturas = 0
        processed_files = 0
        duplicate_files = 0
        error_files = []

        # Procesar cada archivo
        for file in files:
            if not file.filename:
                continue
                
            try:
                filename = secure_filename(file.filename)
                target_folder = batch_folder if batch_folder else user_folder
                filepath = os.path.join(target_folder, filename)
                file.save(filepath)

                # Registrar archivo y validar duplicados
                if tipo_archivo == 'factura-fel-xml':
                    if batch_archivo is not None:
                        ruta = filepath
                        archivo = batch_archivo
                    else:
                        ruta, archivo = register_file(filepath, tipo_archivo, user_id=current_user.id)
                        if ruta is None:
                            duplicate_files += 1
                            # Eliminar archivo duplicado del disco
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            continue

                    factura_result = load_facturas(ruta, archivo, tipo_archivo)
                    total_facturas += factura_result['facturas']
                    total_detalles_factura += factura_result['detalles']
                    duplicate_facturas += factura_result['duplicates']
                else:
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

        # Si el lote no produjo facturas nuevas, quitar registro de archivo-lote para evitar ruido.
        if batch_archivo is not None and total_facturas == 0:
            db.session.delete(batch_archivo)
            db.session.commit()

        # Mostrar resultados
        if processed_files > 0:
            if tipo_archivo == 'factura-fel-xml':
                flash(
                    f'Se procesaron {processed_files} archivo(s). '
                    f'Facturas creadas: {total_facturas}. '
                    f'Detalles de factura: {total_detalles_factura}.',
                    'success'
                )
            else:
                flash(f'Se procesaron {processed_files} archivo(s) con {total_movements} movimientos en total.', 'success')
        
        if duplicate_files > 0:
            flash(f'{duplicate_files} archivo(s) ya habían sido cargados previamente.', 'warning')

        if duplicate_facturas > 0:
            flash(f'{duplicate_facturas} factura(s) ya existían (UUID duplicado).', 'warning')
            
        if error_files:
            flash(f'Error procesando: {"; ".join(error_files)}', 'danger')

        return redirect(url_for('main.index'))

    return render_template('upload.html')
