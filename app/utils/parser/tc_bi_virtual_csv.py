import re
from pathlib import Path
from datetime import datetime
import pandas as pd
from ... import db
from ...models import Movimiento
from .cuenta_utils import get_or_create_cuenta


def load_movements_bi_tc_virtual_csv(filepath, archivo_obj):
    """
    Parser para tarjeta de crédito virtual BI (bicreditonline-DEC25).
    - Lee .xlsx/.xls/.csv con cabeceras tipo: Operación | Movimiento | tipo de | no. doc | concepto | valor | saldo
    - Usa "valor" como monto principal; si falta, recurre a "saldo".
    - CONSUMO/DEBITO -> monto negativo (debito); PAGO/ABONO/EXTORNO -> positivo (credito).
    Devuelve la cantidad de movimientos agregados.
    """
    suffix = Path(filepath).suffix.lower()
    if suffix in ('.xlsx', '.xls'):
        df = pd.read_excel(filepath, header=0)
    elif suffix in ('.csv',):
        try:
            df = pd.read_csv(filepath, header=0, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, header=0, encoding='latin-1')
    else:
        raise ValueError('Formato no soportado para bicreditonline-DEC25')

    if df.empty:
        return 0

    def safe_str(val):
        return str(val).strip() if pd.notna(val) else ''

    def parse_date(value):
        text = safe_str(value)
        if not text:
            return None
        for fmt in ('%d/%m/%Y', '%d/%m/%y', '%m/%d/%Y', '%m/%d/%y'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        parsed = pd.to_datetime(text, dayfirst=True, errors='coerce')
        return parsed.date() if pd.notna(parsed) else None

    def parse_amount(value):
        if pd.isna(value):
            return 0.0
        text = str(value).replace(',', '')
        text = re.sub(r'[^0-9\.-]', '', text)
        if text in ('', '-', '.', '--'):
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    # Normalizar cabeceras
    header_norm = [safe_str(c).upper() for c in df.columns]
    df.columns = header_norm

    ren = {
        'OPERACIÓN': 'fecha_operacion',
        'OPERACION': 'fecha_operacion',
        'MOVIMIENTO': 'fecha_movimiento',
        'TIPO DE': 'tipo',
        'TIPO': 'tipo',
        'NO. DOC': 'documento',
        'NO. DOC.': 'documento',
        'CONCEPTO': 'descripcion',
        'VALOR': 'valor',
        'SALDO': 'saldo',
    }

    mapped_cols = {}
    for col in df.columns:
        key = col.upper()
        if key in ren:
            mapped_cols[col] = ren[key]
    df = df.rename(columns=mapped_cols)

    archivo_obj.tipo_cuenta = 'TC'
    archivo_obj.numero_cuenta = archivo_obj.numero_cuenta or 'BI-Virtual'
    archivo_obj.titular = archivo_obj.titular or 'Desconocido'
    archivo_obj.moneda = 'GTQ'
    db.session.commit()

    cuenta = get_or_create_cuenta(archivo_obj, preferred_tipo='TC')

    count = 0
    for _, row in df.iterrows():
        fecha = parse_date(row.get('fecha_movimiento')) or parse_date(row.get('fecha_operacion'))
        if not fecha:
            continue

        desc = safe_str(row.get('descripcion'))
        tipo_raw = safe_str(row.get('tipo')).upper()
        numero_doc = safe_str(row.get('documento'))

        monto_base = parse_amount(row.get('valor'))
        if monto_base == 0:
            monto_base = parse_amount(row.get('saldo'))
        if monto_base == 0:
            continue

        is_credit = any(token in tipo_raw for token in ['PAGO', 'ABONO', 'EXTORNO', 'CREDITO', 'CRÉDITO'])
        if is_credit:
            monto = abs(monto_base)
            tipo_mov = 'credito'
        else:
            monto = -abs(monto_base)
            tipo_mov = 'debito'

        mov = Movimiento(
            fecha=fecha,
            descripcion=desc,
            numero_documento=numero_doc,
            monto=monto,
            moneda='GTQ',
            tipo=tipo_mov,
            cuenta_id=cuenta.id if cuenta else None,
            archivo_id=archivo_obj.id
        )
        if getattr(archivo_obj, 'user_id', None) is not None:
            mov.user_id = archivo_obj.user_id
        db.session.add(mov)
        count += 1

    db.session.commit()
    return count
