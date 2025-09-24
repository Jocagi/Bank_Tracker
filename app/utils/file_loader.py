import os
import hashlib
from .. import db
from ..models import Archivo
from .parser.monet_aho_gyt_xlsx import load_movements_monet_aho_gyt_xlsx
from .parser.monet_aho_gyt_pdf import load_movements_monet_aho_gyt_pdf
from .parser.tc_gyt_xlsx import load_movements_tc_gyt_xlsx
from .parser.tc_gyt_pdf import load_movements_tc_gyt_pdf
from .parser.monet_bi_pdf import load_movements_bi_monet_pdf
from .parser.tc_bi_xls import load_movements_bi_tc_xls
from .parser.tc_promerica_xls import load_movements_promerica_tc_xls
from .parser.tc_bac_csv import load_movements_bac_tc_csv
from .classifier import clasificar_movimientos


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
    elif tipo_archivo == 'tc-bi':
        archivo_obj.banco = 'BI'
        if extension in ('.xls', '.xlsx'):
            count = load_movements_bi_tc_xls(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-bi.')
    elif tipo_archivo == 'tc-promerica':
        archivo_obj.banco = 'Promerica'
        if extension in ('.xls', '.xlsx'):
            count = load_movements_promerica_tc_xls(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-promerica.')
    elif tipo_archivo == 'tc-bac':
        archivo_obj.banco = 'BAC'
        if extension in ('.csv',):
            count = load_movements_bac_tc_csv(filepath, archivo_obj)
        else:
            raise ValueError('Extensión no válida para formato tc-bac.')
    else:
        raise ValueError(f'Tipo de archivo "{tipo_archivo}" no soportado.')

    # 3) Clasificar todos los movimientos nuevos
    clasificar_movimientos()

    return count
