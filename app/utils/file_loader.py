import os
import hashlib
from datetime import datetime
from .. import db
from ..models import Archivo, Factura, FacturaDetalle
from .parser.monet_aho_gyt_xlsx import load_movements_monet_aho_gyt_xlsx
from .parser.monet_aho_gyt_pdf import load_movements_monet_aho_gyt_pdf
from .parser.tc_gyt_xlsx import load_movements_tc_gyt_xlsx
from .parser.tc_gyt_pdf import load_movements_tc_gyt_pdf
from .parser.monet_bi_pdf import load_movements_bi_monet_pdf
from .parser.monet_bi_email_pdf import load_movements_bi_monet_email_pdf
from .parser.monet_bi_legacy_pdf import parse_monet_bi_legacy_pdf_file
from .parser.monet_bi_ec_integrado_pdf import load_movements_monet_bi_ec_integrado_pdf
from .parser.tc_bi_xls import load_movements_bi_tc_xls
from .parser.tc_bi_email_pdf import load_movements_bi_tc_email_pdf
from .parser.tc_promerica_xls import load_movements_promerica_tc_xls
from .parser.tc_bac_csv import load_movements_bac_tc_csv
from .parser.tc_bi_virtual_xls import load_movements_bi_tc_virtual_xls
from .parser.generic_movimientos import load_movements_generic
from .parser.ahorro_interbanco_pdf import parse_ahorro_interbanco_pdf_file
from .classifier import clasificar_movimientos
from .parser.facturas_fel_xml import parse_factura_fel_xml


def compute_file_hash(filepath):
    """Calcula el hash SHA256 de un archivo para evitar duplicados."""
    hash_sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha.update(chunk)
    return hash_sha.hexdigest()


def register_file(filepath, tipo_archivo, user_id=None):
    """
    Registra un archivo en la DB si no existe duplicado y devuelve (ruta, Archivo).
    Si ya existe, devuelve (None, Archivo existente).
    """
    file_hash = compute_file_hash(filepath)
    existing = Archivo.query.filter_by(file_hash=file_hash).first()
    if existing:
        return None, existing

    nuevo = Archivo(
        tipo_archivo=tipo_archivo,
        filename=os.path.basename(filepath),
        file_hash=file_hash
    )
    # asignar propietario si se proporciona
    if user_id is not None:
        nuevo.user_id = user_id
    db.session.add(nuevo)
    db.session.commit()
    return filepath, nuevo


def register_batch_folder(folderpath, tipo_archivo, user_id=None):
    """
    Registra una carpeta/lote como un único Archivo.
    Útil para cargas masivas de facturas en una subcarpeta.
    """
    basename = os.path.basename(folderpath.rstrip(os.sep))
    raw = f"batch::{tipo_archivo}::{folderpath}::{datetime.utcnow().isoformat()}"
    batch_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    nuevo = Archivo(
        tipo_archivo=tipo_archivo,
        filename=basename,
        file_hash=batch_hash,
    )
    if user_id is not None:
        nuevo.user_id = user_id

    db.session.add(nuevo)
    db.session.commit()
    return nuevo


def load_movements(filepath, archivo_obj, tipo_archivo):
    """
    Lee el archivo indicado por `tipo_archivo`, lo parsea con el parser correspondiente,
    guarda los movimientos en la BD y aplica clasificación.
    """

    # 1) Verificar extensión
    extension = os.path.splitext(filepath)[1].lower()

    # 2) Dispatch al parser concreto
    if tipo_archivo == 'monet-aho-gyt':
        archivo_obj.banco = 'GYT'
        if extension in ('.xlsx', '.xls'):
            count = load_movements_monet_aho_gyt_xlsx(filepath, archivo_obj)
        elif extension in ('.pdf',):
            count = load_movements_monet_aho_gyt_pdf(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato monet-aho-gyt.')
    elif tipo_archivo == 'tc-gyt':
        archivo_obj.banco = 'GYT'
        if extension in ('.xlsx', '.xls'):
            count = load_movements_tc_gyt_xlsx(filepath, archivo_obj)
        elif extension in ('.pdf',):
            count = load_movements_tc_gyt_pdf(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-gyt.')
    elif tipo_archivo == 'monet-bi':
        archivo_obj.banco = 'BI'
        if extension in ('.pdf',):
            count = load_movements_bi_monet_pdf(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato monet-bi.')
    elif tipo_archivo == 'monet-bi-email':
        archivo_obj.banco = 'BI'
        if extension in ('.pdf',):
            count = load_movements_bi_monet_email_pdf(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato monet-bi-email.')
    elif tipo_archivo == 'monet-bi-legacy':
        archivo_obj.banco = 'BI'
        if extension in ('.pdf',):
            count = parse_monet_bi_legacy_pdf_file(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato monet-bi-legacy.')
    elif tipo_archivo in ('monet_bi_ec_integrado', 'monet-bi-ec-integrado'):
        archivo_obj.banco = 'BI'
        if extension in ('.pdf',):
            count = load_movements_monet_bi_ec_integrado_pdf(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato monet_bi_ec_integrado.')
    elif tipo_archivo == 'tc-bi':
        archivo_obj.banco = 'BI'
        if extension in ('.xls', '.xlsx'):
            count = load_movements_bi_tc_xls(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-bi.')
    elif tipo_archivo == 'tc-bi-email':
        archivo_obj.banco = 'BI'
        if extension in ('.pdf',):
            count = load_movements_bi_tc_email_pdf(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-bi-email.')
    elif tipo_archivo == 'tc-promerica':
        archivo_obj.banco = 'Promerica'
        if extension in ('.xls', '.xlsx'):
            count = load_movements_promerica_tc_xls(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-promerica.')
    elif tipo_archivo == 'tc-online-bi':
        archivo_obj.banco = 'BI'
        if extension in ('.xls', '.xlsx'):
            count = load_movements_bi_tc_virtual_xls(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-online-bi.')
    elif tipo_archivo == 'generic-movimientos':
        if extension in ('.xls', '.xlsx', '.csv'):
            count = load_movements_generic(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato generic-movimientos.')
    elif tipo_archivo == 'tc-bac':
        archivo_obj.banco = 'BAC'
        if extension in ('.csv',):
            count = load_movements_bac_tc_csv(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-bac.')
    elif tipo_archivo == 'ahorro-interbanco':
        archivo_obj.banco = 'Interbanco'
        if extension in ('.pdf',):
            count = parse_ahorro_interbanco_pdf_file(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato ahorro-interbanco.')
    else:
        raise ValueError(f'Tipo de archivo "{tipo_archivo}" no soportado.')

    # 3) Clasificar todos los movimientos nuevos
    clasificar_movimientos()

    return count


def load_facturas(filepath, archivo_obj, tipo_archivo):
    """
    Carga facturas FEL XML en estructura separada de movimientos.
    Retorna un dict con el resultado de la importación.
    """
    extension = os.path.splitext(filepath)[1].lower()
    if extension not in ('.xml',):
        raise ValueError('Extensión no válida para facturas FEL. Se espera .xml')

    if tipo_archivo != 'factura-fel-xml':
        raise ValueError(f'Tipo de archivo "{tipo_archivo}" no soportado para facturas.')

    parsed = parse_factura_fel_xml(filepath)
    factura_data = parsed['factura']
    detalles_data = parsed['detalles']

    existing = Factura.query.filter_by(uuid=factura_data['uuid']).first()
    if existing:
        return {
            'facturas': 0,
            'detalles': 0,
            'duplicates': 1,
        }

    factura = Factura(
        uuid=factura_data['uuid'],
        serie=factura_data['serie'],
        numero_autorizacion=factura_data['numero_autorizacion'],
        tipo_documento=factura_data['tipo_documento'],
        fecha_emision=factura_data['fecha_emision'],
        fecha_certificacion=factura_data['fecha_certificacion'],
        moneda=factura_data['moneda'],
        emisor_nit=factura_data['emisor_nit'],
        emisor_nombre=factura_data['emisor_nombre'],
        receptor_id=factura_data['receptor_id'],
        receptor_nombre=factura_data['receptor_nombre'],
        gran_total=factura_data['gran_total'],
        total_impuesto_iva=factura_data['total_impuesto_iva'],
        retencion_isr=factura_data['retencion_isr'],
        retencion_iva=factura_data['retencion_iva'],
        total_menos_retenciones=factura_data['total_menos_retenciones'],
        archivo_id=archivo_obj.id,
        user_id=archivo_obj.user_id,
    )
    db.session.add(factura)
    db.session.flush()

    detalle_count = 0
    for d in detalles_data:
        db.session.add(FacturaDetalle(
            factura_id=factura.id,
            numero_linea=d['numero_linea'],
            descripcion=d['descripcion'],
            cantidad=d['cantidad'],
            unidad_medida=d['unidad_medida'],
            precio_unitario=d['precio_unitario'],
            total_linea=d['total_linea'],
        ))
        detalle_count += 1

    db.session.commit()

    return {
        'facturas': 1,
        'detalles': detalle_count,
        'duplicates': 0,
    }
