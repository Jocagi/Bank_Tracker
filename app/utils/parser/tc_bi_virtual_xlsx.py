import re
from datetime import datetime
import pandas as pd
from ... import db
from ...models import Movimiento
from .cuenta_utils import get_or_create_cuenta


def load_movements_bi_tc_virtual_xls(filepath, archivo_obj):
    """
    Parser para tarjeta de crédito virtual BI (bicreditonline-DEC25) en Excel (.xls/.xlsx).
    Estructura esperada:
      - Fila 0: Metadatos (titular en col 1, número en col 3)
      - Fila 1: Vacía
      - Fila 2: Cabeceras (Operación | Movimiento | tipo de movimiento | no. doc | concepto | valor | saldo)
      - Fila 3+: Movimientos
    - Determina débito/crédito por tipo: CONSUMO/DEBITO -> débito negativo; PAGO/ABONO/EXTORNO -> crédito positivo
    Devuelve la cantidad de movimientos agregados.
    """
    df = pd.read_excel(filepath, header=None)
    
    if df.empty:
        return 0

    def safe_str(val):
        return str(val).strip() if pd.notna(val) else ''

    def parse_date(value):
        text = safe_str(value)
        if not text:
            return None
        try:
            return pd.to_datetime(text, dayfirst=True).date()
        except (ValueError, TypeError):
            return None

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

    # Extraer metadatos de fila 0
    titular = safe_str(df.iloc[0, 1]) if len(df) > 0 and len(df.columns) > 1 else archivo_obj.titular or 'Desconocido'
    numero_cuenta = safe_str(df.iloc[0, 3]) if len(df) > 0 and len(df.columns) > 3 else archivo_obj.numero_cuenta or 'BI-Virtual'

    archivo_obj.tipo_cuenta = 'TC'
    archivo_obj.numero_cuenta = numero_cuenta
    archivo_obj.titular = titular
    archivo_obj.moneda = 'GTQ'
    db.session.commit()

    cuenta = get_or_create_cuenta(archivo_obj, preferred_tipo='TC')

    # Procesar movimientos desde fila 3 en adelante
    count = 0
    for idx in range(3, len(df)):
        row = df.iloc[idx]
        
        fecha = parse_date(row.iloc[0])
        if not fecha:
            break  # Detener al encontrar fila sin fecha

        tipo_raw = safe_str(row.iloc[2]).upper()  # Columna "tipo de movimiento"
        descripcion = safe_str(row.iloc[4])       # Columna "concepto"
        numero_doc = safe_str(row.iloc[3])        # Columna "no. doc"
        monto_valor = parse_amount(row.iloc[5])   # Columna "valor"

        if monto_valor == 0:
            continue

        # Determinar si es crédito o débito
        is_credit = any(token in tipo_raw for token in ['PAGO', 'ABONO', 'EXTORNO', 'CREDITO', 'CRÉDITO'])
        if is_credit:
            monto = abs(monto_valor)
            tipo_mov = 'credito'
        else:
            monto = -abs(monto_valor)
            tipo_mov = 'debito'

        mov = Movimiento(
            fecha=fecha,
            descripcion=descripcion,
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
