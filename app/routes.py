import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
from . import db
from .models import Archivo, Categoria, Comercio, Movimiento, Regla, Cuenta, TipoCambio
from .utils.file_loader import register_file, load_movements
from .utils.classifier import reclasificar_movimientos

bp = Blueprint('main', __name__)

from sqlalchemy.orm import joinedload
from sqlalchemy import func

@bp.route('/')
def index():
    # Lectura de filtros desde query string
    start               = request.args.get('start_date', '')
    end                 = request.args.get('end_date', '')
    desc                = request.args.get('desc', '')
    selected_cuenta     = request.args.get('cuenta_id', '')
    selected_comercio   = request.args.get('comercio_id', '')
    selected_categoria  = request.args.get('categoria_id', '')
    selected_tipo_cont  = request.args.get('tipo_contabilizacion', '')

    # Base de la consulta con eager loading
    query = Movimiento.query.options(
        joinedload(Movimiento.comercio)
                   .joinedload(Comercio.categoria),
        joinedload(Movimiento.cuenta)
    )

    # Filtros existentes...
    if start:
        try:
            d1 = datetime.strptime(start, '%Y-%m-%d').date()
            query = query.filter(Movimiento.fecha >= d1)
        except ValueError:
            flash('Fecha “Desde” inválida', 'warning')
    if end:
        try:
            d2 = datetime.strptime(end, '%Y-%m-%d').date()
            query = query.filter(Movimiento.fecha <= d2)
        except ValueError:
            flash('Fecha “Hasta” inválida', 'warning')
    if desc:
        query = query.filter(Movimiento.descripcion.ilike(f'%{desc}%'))
    if selected_comercio:
        query = query.filter(Movimiento.comercio_id == int(selected_comercio))
    if selected_categoria:
        query = query.filter(
            Movimiento.comercio.has(categoria_id=int(selected_categoria))
        )
    if selected_tipo_cont:
        query = query.filter(
            Movimiento.comercio.has(tipo_contabilizacion=selected_tipo_cont)
        )

    # --- Nuevo filtro por Cuenta ---
    if selected_cuenta:
        query = query.filter(Movimiento.cuenta_id == int(selected_cuenta))

    # Obtener los movimientos
    movimientos = (
        query.order_by(Movimiento.fecha.desc())
             .limit(100)
             .all()
    )

    # Totales
    total_movs  = len(movimientos)
    sum_debito  = sum(m.monto for m in movimientos if m.tipo == 'debito')
    sum_credito = sum(m.monto for m in movimientos if m.tipo == 'credito')

    # Opciones para los selects
    cuentas     = Cuenta.query.order_by(Cuenta.numero_cuenta).all()
    comercios   = Comercio.query.order_by(Comercio.nombre).all()
    categorias  = Categoria.query.order_by(Categoria.nombre).all()
    tipos       = ['ingresos', 'gastos', 'transferencias']

    return render_template(
        'index.html',
        movimientos=movimientos,
        total_movs=total_movs,
        sum_debito=sum_debito,
        sum_credito=sum_credito,
        # valores actuales de los filtros
        start_date=start,
        end_date=end,
        desc_query=desc,
        selected_cuenta=selected_cuenta,
        selected_comercio=selected_comercio,
        selected_categoria=selected_categoria,
        selected_tipo_cont=selected_tipo_cont,
        # listas para los selects
        cuentas=cuentas,
        comercios=comercios,
        categorias=categorias,
        tipos_contabilizacion=tipos
    )


# app/routes.py

@bp.route('/dashboard')
def dashboard():
    # ————————————————————————————————————————
    # 1) Leer filtros desde la query string
    start   = request.args.get('start_date', '')
    end     = request.args.get('end_date', '')
    cat_id  = request.args.get('category_id', '')

    d_start = d_end = None
    if start:
        try:
            d_start = datetime.strptime(start, '%Y-%m-%d').date()
        except ValueError:
            flash('Fecha “Desde” inválida', 'warning')
    if end:
        try:
            d_end = datetime.strptime(end, '%Y-%m-%d').date()
        except ValueError:
            flash('Fecha “Hasta” inválida', 'warning')

    # ————————————————————————————————————————
    # 2) Lista de categorías para el dropdown
    categorias = Categoria.query.order_by(Categoria.nombre).all()

    # ————————————————————————————————————————
    # 3) Gastos por Comercio (GTQ)
    commerce_q = (
        db.session.query(
            Comercio.nombre,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .order_by(func.sum(Movimiento.monto * TipoCambio.valor).asc())
    )
    if d_start:
        commerce_q = commerce_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        commerce_q = commerce_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        commerce_q = commerce_q.join(Categoria)\
                               .filter(Categoria.id == int(cat_id))

    commerce_data = commerce_q.group_by(Comercio.id).all()
    if commerce_data:
        commerce_labels, commerce_values = zip(*commerce_data)
    else:
        commerce_labels = commerce_values = []

    commerce_table = [
        (lbl, abs(total)) for lbl, total in commerce_data
    ]

    # ————————————————————————————————————————
    # 4) Gastos por Categoría (GTQ)
    cat_q = (
        db.session.query(
            Categoria.nombre,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Comercio, Comercio.categoria_id == Categoria.id)
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
        .order_by(func.sum(Movimiento.monto * TipoCambio.valor).asc())
    )
    if d_start:
        cat_q = cat_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        cat_q = cat_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        cat_q = cat_q.filter(Categoria.id == int(cat_id))

    cat_data = cat_q.group_by(Categoria.id).all()
    if cat_data:
        cat_labels, cat_values = zip(*cat_data)
    else:
        cat_labels = cat_values = []

    category_table = [
        (lbl, abs(total)) for lbl, total in cat_data
    ]

    # ————————————————————————————————————————
    # 5) Evolución Mensual de Gastos (GTQ)
    month_q = (
        db.session.query(
            func.strftime('%Y-%m', Movimiento.fecha).label('mes'),
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Comercio, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'gastos')
    )
    if d_start:
        month_q = month_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        month_q = month_q.filter(Movimiento.fecha <= d_end)
    if cat_id:
        month_q = month_q.filter(Comercio.categoria_id == int(cat_id))

    month_data = month_q.group_by('mes').order_by('mes').all()
    if month_data:
        month_labels, raw_vals = zip(*month_data)
        month_values = [abs(v) for v in raw_vals]
    else:
        month_labels = month_values = []

    # ————————————————————————————————————————
    # 6) **Ingresos por Comercio (GTQ)**
    income_q = (
        db.session.query(
            Comercio.nombre,
            func.sum(Movimiento.monto * TipoCambio.valor).label('total_gtq')
        )
        .join(Movimiento, Movimiento.comercio_id == Comercio.id)
        .join(TipoCambio, TipoCambio.moneda == Movimiento.moneda)
        .filter(Comercio.tipo_contabilizacion == 'ingresos')
    )
    if d_start:
        income_q = income_q.filter(Movimiento.fecha >= d_start)
    if d_end:
        income_q = income_q.filter(Movimiento.fecha <= d_end)
    # los ingresos no dependen de cat_id, pero si se quisiera:
    # if cat_id:
    #     income_q = income_q.join(Categoria).filter(Categoria.id==int(cat_id))

    income_data = income_q.group_by(Comercio.id).all()
    income_table = [
        (lbl, abs(total)) for lbl, total in income_data
    ]

    # ————————————————————————————————————————
    return render_template('dashboard.html',
        # Charts de gastos
        commerce_labels=list(commerce_labels),
        commerce_values=list(commerce_values),
        cat_labels=list(cat_labels),
        cat_values=list(cat_values),
        month_labels=list(month_labels),
        month_values=list(month_values),
        # Tablas de gastos
        commerce_table=commerce_table,
        category_table=category_table,
        # **Tabla de ingresos**
        income_table=income_table,
        # Filtros
        categorias=categorias,
        start_date=start,
        end_date=end,
        selected_cat=cat_id
    )


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

@bp.route('/comercios')
def list_comercios():
    #Obterner todos los comercios y sus reglas
    comercios = Comercio.query.all()
    for comercio in comercios:
        # Cargar reglas para cada comercio
        comercio.reglas = Regla.query.filter_by(comercio_id=comercio.id).all()
    # Ordenar por nombre
    comercios.sort(key=lambda c: c.nombre.lower())
    return render_template('comercios.html', comercios=comercios)

@bp.route('/comercios/add', methods=['GET', 'POST'])
def add_comercio():
    categorias = Categoria.query.all()
    if request.method == 'POST':
        nombre = request.form['nombre']
        categoria_id = request.form['categoria_id']
        tipo_contabilizacion  = request.form['tipo_contabilizacion']

        # Crear nuevo comercio
        nuevo_comercio = Comercio(
            nombre=nombre,
            categoria_id=categoria_id,
            tipo_contabilizacion=tipo_contabilizacion
        )
        db.session.add(nuevo_comercio)
        db.session.flush()  # Para obtener nuevo_comercio.id

        # Procesar reglas de clasificación
        descripciones = request.form.getlist('reg_descripcion')
        tipos = request.form.getlist('reg_tipo')
        criterios = request.form.getlist('reg_criterio')
        for desc, tp, crit in zip(descripciones, tipos, criterios):
            desc = desc.strip()
            crit = crit.strip()
            if desc and crit:
                regla = Regla(
                    comercio_id=nuevo_comercio.id,
                    descripcion=desc,
                    tipo=tp,
                    criterio=crit
                )
                db.session.add(regla)
        db.session.commit()

        # Clasificar movimientos automáticamente
        reclasificar_movimientos()

        flash('Comercio y reglas agregados correctamente.', 'success')
        return redirect(url_for('main.list_comercios'))
    return render_template('comercios_add.html', categorias=categorias)


@bp.route('/comercios/<int:comercio_id>/edit', methods=['GET', 'POST'])
def edit_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    categorias = Categoria.query.all()
    if request.method == 'POST':
        comercio.nombre = request.form['nombre']
        comercio.categoria_id = request.form['categoria_id']
        comercio.tipo_contabilizacion = request.form['tipo_contabilizacion']
        
        # Eliminar reglas antiguas
        Regla.query.filter_by(comercio_id=comercio.id).delete()
        
        # Agregar reglas nuevas
        for desc, tp, crit in zip(
            request.form.getlist('reg_descripcion'),
            request.form.getlist('reg_tipo'),
            request.form.getlist('reg_criterio')
        ):
            if desc.strip() and crit.strip():
                db.session.add(Regla(
                    comercio_id=comercio.id,
                    descripcion=desc.strip(),
                    tipo=tp,
                    criterio=crit.strip()
                ))
        db.session.commit()
        
        # Re-clasificar todos los movimientos tras modificar reglas
        reclasificar_movimientos()

        flash('Comercio actualizado', 'success')
        return redirect(url_for('main.list_comercios'))
    return render_template('comercios_edit.html', comercio=comercio, categorias=categorias)

@bp.route('/comercios/<int:comercio_id>/delete', methods=['POST'])
def delete_comercio(comercio_id):
    comercio = Comercio.query.get_or_404(comercio_id)
    db.session.delete(comercio)
    db.session.commit()
    reclasificar_movimientos()
    flash('Comercio eliminado', 'warning')
    return redirect(url_for('main.list_comercios'))

@bp.route('/categorias')
def list_categorias():
    categorias = Categoria.query.all()
    return render_template('categorias.html', categorias=categorias)

@bp.route('/categorias/add', methods=['GET', 'POST'])
def add_categoria():
    if request.method == 'POST':
        nombre = request.form['nombre']
        nueva = Categoria(nombre=nombre)
        db.session.add(nueva)
        db.session.commit()
        flash('Categoría agregada correctamente.', 'success')
        return redirect(url_for('main.list_categorias'))
    return render_template('categorias_add.html')

@bp.route('/categorias/<int:categoria_id>/edit', methods=['GET', 'POST'])
def edit_categoria(categoria_id):
    categoria = Categoria.query.get_or_404(categoria_id)
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        if not nombre:
            flash('El nombre no puede quedar vacío.', 'danger')
        elif Categoria.query.filter(Categoria.nombre==nombre, Categoria.id!=categoria.id).first():
            flash('Ya existe otra categoría con ese nombre.', 'warning')
        else:
            categoria.nombre = nombre
            db.session.commit()
            flash('Categoría actualizada correctamente.', 'success')
            return redirect(url_for('main.list_categorias'))
    return render_template('categorias_edit.html', categoria=categoria)

@bp.route('/categorias/<int:categoria_id>/delete', methods=['POST'])
def delete_categoria(categoria_id):
    categoria = Categoria.query.get_or_404(categoria_id)
    db.session.delete(categoria)
    db.session.commit()
    flash('Categoría eliminada.', 'warning')
    return redirect(url_for('main.list_categorias'))

@bp.route('/sin_clasificar', methods=['GET'])
def sin_clasificar():
    movimientos = Movimiento.query.filter_by(comercio_id=None).all()
    comercios   = Comercio.query.order_by(Comercio.nombre).all()
    return render_template('sin_clasificar.html',
                           movimientos=movimientos,
                           comercios=comercios)

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

# Listar
@bp.route('/tipos_cambio')
def list_tipos_cambio():
    tipos = TipoCambio.query.order_by(TipoCambio.moneda).all()
    return render_template('tipos_cambio.html', tipos=tipos)

# Agregar
@bp.route('/tipos_cambio/add', methods=['GET','POST'])
def add_tipo_cambio():
    if request.method == 'POST':
        moneda = request.form['moneda'].strip().upper()
        try:
            valor = float(request.form['valor'])
        except ValueError:
            flash('Valor de tipo de cambio inválido.', 'danger')
            return redirect(url_for('main.add_tipo_cambio'))
        if not moneda:
            flash('La moneda no puede quedar vacía.', 'danger')
        elif TipoCambio.query.filter_by(moneda=moneda).first():
            flash('Ya existe ese tipo de cambio.', 'warning')
        else:
            tc = TipoCambio(moneda=moneda, valor=valor)
            db.session.add(tc)
            db.session.commit()
            flash('Tipo de cambio agregado.', 'success')
            return redirect(url_for('main.list_tipos_cambio'))
    return render_template('tipo_cambio_add.html')

# Editar
@bp.route('/tipos_cambio/<int:tc_id>/edit', methods=['GET','POST'])
def edit_tipo_cambio(tc_id):
    tc = TipoCambio.query.get_or_404(tc_id)
    if request.method == 'POST':
        try:
            valor = float(request.form['valor'])
        except ValueError:
            flash('Valor de tipo de cambio inválido.', 'danger')
            return redirect(url_for('main.edit_tipo_cambio', tc_id=tc.id))
        tc.valor = valor
        db.session.commit()
        flash('Tipo de cambio actualizado.', 'success')
        return redirect(url_for('main.list_tipos_cambio'))
    return render_template('tipo_cambio_edit.html', tc=tc)

# Eliminar
@bp.route('/tipos_cambio/<int:tc_id>/delete', methods=['POST'])
def delete_tipo_cambio(tc_id):
    tc = TipoCambio.query.get_or_404(tc_id)
    db.session.delete(tc)
    db.session.commit()
    flash('Tipo de cambio eliminado.', 'warning')
    return redirect(url_for('main.list_tipos_cambio'))
