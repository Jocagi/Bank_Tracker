import re
from datetime import datetime
import pandas as pd
from ... import db
from ...models import Movimiento
from .cuenta_utils import get_or_create_cuenta


def load_movements_generic(filepath, archivo_obj):
    """
    Parser genérico para movimientos.
        Formato esperado (csv/xlsx): columnas con encabezados al menos:
            cuenta, titular, moneda_cuenta, fecha, descripcion, monto, tipo, moneda, numero_documento (opcional)
        - tipo: debito/cargo -> monto negativo; credito/abono/pago -> monto positivo
    - moneda de movimiento opcional; si falta se usa moneda_cuenta
    Devuelve la cantidad de movimientos cargados.
    """
    ext = filepath.lower().split('.')[-1]
    if ext in ('xlsx', 'xls'):
        df = pd.read_excel(filepath)
    elif ext == 'csv':
        try:
            df = pd.read_csv(filepath, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding='latin-1')
    else:
        raise ValueError('Extensión no soportada para genérico (use .xlsx o .csv).')

    if df.empty:
        return 0

    def safe_str(val):
        return str(val).strip() if pd.notna(val) else ''

    def parse_date(val):
        text = safe_str(val)
        if not text:
            return None
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%m/%d/%Y', '%m/%d/%y'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        parsed = pd.to_datetime(text, dayfirst=True, errors='coerce')
        return parsed.date() if pd.notna(parsed) else None

    def parse_amount(val):
        if pd.isna(val):
            return 0.0
        text = str(val).replace(',', '')
        text = re.sub(r'[^0-9\.-]', '', text)
        if text in ('', '-', '.', '--'):
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    # Normalizar cabeceras
    ren = {
        'CUENTA': 'cuenta', 'NUMERO_CUENTA': 'cuenta', 'NÚMERO_CUENTA': 'cuenta',
        'TITULAR': 'titular',
        'MONEDA_CUENTA': 'moneda_cuenta', 'MONEDA': 'moneda',
        'FECHA': 'fecha',
        'DESCRIPCION': 'descripcion', 'DESCRIPCIÓN': 'descripcion', 'DESCRIPCIÓN ': 'descripcion',
        'MONTO': 'monto',
        'TIPO': 'tipo',
        'MONEDA_MOV': 'moneda_mov', 'MONEDA_MOVIMIENTO': 'moneda_movimiento',
        'NUMERO_DOCUMENTO': 'numero_documento', 'NÚMERO_DOCUMENTO': 'numero_documento', 'NO. DOC': 'numero_documento',
    }
    norm_cols = {}
    for col in df.columns:
        key = safe_str(col).upper()
        if key in ren:
            norm_cols[col] = ren[key]
    df = df.rename(columns=norm_cols)

    required = ['cuenta', 'titular', 'fecha', 'descripcion', 'monto', 'tipo']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f'Faltan columnas requeridas: {", ".join(missing)}')

    # Extraer metadatos de la primera fila
    primera_fila = df.iloc[0] if len(df) > 0 else {}
    banco = getattr(archivo_obj, 'banco', None) or 'GEN'
    tipo_cuenta = getattr(archivo_obj, 'tipo_cuenta', None) or 'GEN'
    numero_cuenta = getattr(archivo_obj, 'numero_cuenta', None) or safe_str(primera_fila.get('cuenta')) or 'GEN-000'
    titular = getattr(archivo_obj, 'titular', None) or safe_str(primera_fila.get('titular')) or 'Desconocido'
    moneda = getattr(archivo_obj, 'moneda', None) or safe_str(primera_fila.get('moneda_cuenta')) or safe_str(primera_fila.get('moneda')) or 'GTQ'

    # Crear objeto temporal para get_or_create_cuenta
    class TempArchivo:
        pass
    
    temp_obj = TempArchivo()
    temp_obj.banco = banco
    temp_obj.tipo_cuenta = tipo_cuenta
    temp_obj.numero_cuenta = numero_cuenta
    temp_obj.titular = titular
    temp_obj.moneda = moneda
    temp_obj.user_id = getattr(archivo_obj, 'user_id', None)

    count = 0
    for _, row in df.iterrows():
        cuenta_num = safe_str(row.get('cuenta'))
        titular_row = safe_str(row.get('titular')) or titular
        moneda_cuenta = safe_str(row.get('moneda_cuenta')) or safe_str(row.get('moneda')) or moneda

        # Actualizar datos temporales por fila
        temp_obj.numero_cuenta = cuenta_num or numero_cuenta
        temp_obj.titular = titular_row
        temp_obj.moneda = moneda_cuenta

        cuenta = get_or_create_cuenta(temp_obj, preferred_tipo=tipo_cuenta)

        fecha = parse_date(row.get('fecha'))
        if not fecha:
            continue

        desc = safe_str(row.get('descripcion'))
        tipo_raw = safe_str(row.get('tipo')).lower()
        monto_val = parse_amount(row.get('monto'))
        if monto_val == 0:
            continue

        moneda_mov = safe_str(row.get('moneda_mov')) or safe_str(row.get('moneda_movimiento')) or safe_str(row.get('moneda')) or moneda_cuenta or 'GTQ'
        numero_doc = safe_str(row.get('numero_documento'))

        is_credit = any(tok in tipo_raw for tok in ['credito', 'crédito', 'abono', 'pago'])
        monto = abs(monto_val) if is_credit else -abs(monto_val)
        tipo_mov = 'credito' if is_credit else 'debito'

        mov = Movimiento(
            fecha=fecha,
            descripcion=desc,
            numero_documento=numero_doc,
            monto=monto,
            moneda=moneda_mov or 'GTQ',
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