from datetime import datetime
import pandas as pd
from ... import db
from ...models import Archivo, Movimiento, Cuenta
from ..classifier import clasificar_movimientos

def load_movements_monet_aho_gyt_xlsx(filepath, archivo_obj):

    # Leer primera hoja completa sin encabezados
    df = pd.read_excel(filepath, sheet_name=0, header=None)

    # Extraer metadatos del encabezado (filas 0-8)
    header_info = extract_header_monet_aho_gyt_xlsx(df)

    # Estandarizar valores
    if 'moneda' in header_info:
        if header_info['moneda'].upper() == 'QTZ':
            header_info['moneda'] = 'GTQ'
    if 'tipo_cuenta' in header_info:
        if header_info['tipo_cuenta'].upper() == 'MONETARIO':
            header_info['tipo_cuenta'] = 'MONET'
        elif header_info['tipo_cuenta'].upper() == 'AHORRO':
            header_info['tipo_cuenta'] = 'AHO'

    if not header_info:
        raise ValueError("No se encontraron metadatos válidos en el archivo.")
    
    # Guardar metadatos en Archivo
    archivo_obj.banco = archivo_obj.banco
    archivo_obj.tipo_cuenta = header_info.get('tipo_cuenta', 'Desconocido')
    archivo_obj.moneda = header_info.get('moneda', 'Desconocido')
    archivo_obj.numero_cuenta = header_info.get('numero_cuenta', 'Desconocido')
    archivo_obj.titular = header_info.get('titular', 'Desconocido')
    archivo_obj.saldo_inicial = header_info.get('saldo', 0.0)
    db.session.commit()

    # Verificar o crear Cuenta
    cuenta = Cuenta.query.filter_by(
        banco=archivo_obj.banco,
        tipo_cuenta=archivo_obj.tipo_cuenta,
        numero_cuenta=archivo_obj.numero_cuenta
    ).first()
    if not cuenta:
        cuenta = Cuenta(
            banco=archivo_obj.banco,
            tipo_cuenta=header_info.get('tipo_cuenta', 'Desconocido'),
            numero_cuenta=header_info.get('numero_cuenta', 'Desconocido'),
            titular=header_info.get('titular', 'Desconocido'),
            moneda=header_info.get('moneda', 'Desconocido')
        )
        # asignar propietario si el archivo tiene user_id
        if getattr(archivo_obj, 'user_id', None) is not None:
            cuenta.user_id = archivo_obj.user_id
        db.session.add(cuenta)
        db.session.commit()

    movimientos = extract_movements_monet_aho_gyt_xlsx(df, archivo_obj)
    for idx, mov in movimientos.iterrows():

        mg = Movimiento(
            fecha=mov['fecha'],
            descripcion=mov['descripcion'],
            lugar=mov['lugar'],
            numero_documento=mov['documento'],
            monto=mov['monto'],
            moneda=mov['moneda'],
            tipo='debito' if mov['monto'] < 0 else 'credito',
            cuenta_id=cuenta.id,
            archivo_id=archivo_obj.id
        )
        # Propagar propietario del archivo al movimiento
        if getattr(archivo_obj, 'user_id', None) is not None:
            mg.user_id = archivo_obj.user_id
        db.session.add(mg)

    db.session.commit()

    return len(movimientos)

def extract_header_monet_aho_gyt_xlsx(df):
    """
    Extrae metadata (fecha generación, titular, cuenta, saldo) de las primeras filas.
    """
    header = {}
    for i in range(min(9, len(df))):
        cell = str(df.iloc[i, 0])
        if 'Generado el:' in cell:
            date_str = cell.split('Generado el:')[1].strip()
            header['fecha'] = datetime.strptime(date_str, '%d/%m/%Y %H:%M:%S')
        elif 'Nombre de la cuenta:' in cell:
            header['titular'] = cell.split(':', 1)[1].strip()
        elif 'Cuenta:' in cell:
            # Cuenta formato: Cuenta: MONET (QTZ) 34-38089-1
            cuenta = cell.split(':', 1)[1].strip()
            header['tipo_cuenta'] = cuenta.split(' ')[0]
            header['moneda'] = cuenta.split(' ')[1].strip('()')
            header['numero_cuenta'] = cuenta.split(' ')[-1]
        elif 'Saldo total:' in cell:
            saldo_str = cell.split(':', 1)[1].strip().replace(',', '')
            header['saldo'] = float(saldo_str)
    return header


def extract_movements_monet_aho_gyt_xlsx(df, archivo_obj):
    """
    Procesa movimientos que inician en la fila 10 con cabecera fija:
    Fecha, Descripción, Lugar, Débito, Crédito, Saldo.
    Lee hasta la primera línea completamente vacía.
    """
    # Definir cabeceras
    cols = ['fecha', 'descripcion', 'lugar', 'debito', 'credito', 'saldo']
    # Data desde índice 8 (fila 9)
    mov_df = df.iloc[8:].copy()
    mov_df.columns = cols
    # Eliminar la fila de cabecera
    mov_df = mov_df.iloc[1:].reset_index(drop=True)

    # Detectar primera fila vacía
    blank_mask = mov_df[cols].isna().all(axis=1)
    if blank_mask.any():
        first_blank = blank_mask.idxmax()
        mov_df = mov_df.loc[:first_blank-1]

    # Filtrar filas con fecha
    mov_df = mov_df[mov_df['fecha'].notna()].copy()
    # Convertir fecha
    mov_df['fecha'] = pd.to_datetime(mov_df['fecha'], dayfirst=True).dt.date
    # Calcular monto: crédito - débito
    mov_df['monto'] = mov_df['credito'].fillna(0) - mov_df['debito'].fillna(0)
    # Moneda y documento
    mov_df['moneda'] = archivo_obj.moneda
    mov_df['documento'] = None
    # Descripción y lugar
    mov_df['descripcion'] = mov_df['descripcion'].fillna('')
    mov_df['lugar'] = mov_df['lugar'].fillna('')
    # Mantener línea original
    mov_df['__linea'] = mov_df.index + 10  # referencia de fila en el archivo
    # Seleccionar columnas finales
    return mov_df[['fecha', 'descripcion', 'lugar', 'monto', 'moneda', 'documento', '__linea']]