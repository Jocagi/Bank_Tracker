
import pandas as pd
from ... import db
from ...models import Movimiento, Cuenta
from ..classifier import clasificar_movimientos

def load_movements_tc_gyt_xlsx(filepath, archivo_obj):
    """
    Parser unificado para estado de cuenta de Tarjeta de Crédito GYT (.xlsx):
      1) Extrae metadata de cuenta de las primeras filas.
      2) Actualiza archivo_obj y crea/recupera Cuenta.
      3) Detecta la cabecera de movimientos (buscando 'Fecha' y 'Descripción'),
         luego lee desde ahí, deteniéndose en la primera fila vacía.
      4) Normaliza, persiste Movimientos y reclasifica.
    Devuelve el número de movimientos cargados.
    """
    # 1) Leer hoja 0 sin cabeceras, todo como string
    df0 = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)

    # 2) Extraer metadata de cuenta de las primeras 13 filas
    titular = numero = None
    for i in range(min(13, len(df0))):
        for cell in df0.iloc[i].dropna().astype(str):
            txt = cell.strip()
            if txt.startswith('Nombre de la cuenta:'):
                titular = txt.split(':',1)[1].strip()
            elif txt.startswith('Tarjeta'):
                numero = txt.split(' ',2)[1].strip()
    cuenta_tipo = 'TC'
    moneda = 'GTQ|USD'

    # 3) Actualizar metadatos en archivo_obj
    archivo_obj.tipo_cuenta   = cuenta_tipo
    archivo_obj.numero_cuenta = numero or archivo_obj.numero_cuenta
    archivo_obj.titular       = titular or archivo_obj.titular
    archivo_obj.moneda        = moneda
    db.session.commit()

    # 4) Crear o recuperar la cuenta
    cuenta = Cuenta.query.filter_by(
        banco=archivo_obj.banco,
        tipo_cuenta=archivo_obj.tipo_cuenta,
        numero_cuenta=archivo_obj.numero_cuenta
    ).first()
    if not cuenta:
        cuenta = Cuenta(
            banco=archivo_obj.banco,
            tipo_cuenta=archivo_obj.tipo_cuenta,
            numero_cuenta=archivo_obj.numero_cuenta,
            titular=archivo_obj.titular,
            moneda=archivo_obj.moneda
        )
        db.session.add(cuenta)
        db.session.commit()

    # 5) Buscar el índice de la fila de cabecera (contiene 'Fecha' y 'Descripción')
    header_idx = None
    for i, row in df0.iterrows():
        vals = row.dropna().astype(str).tolist()
        if 'Fecha' in vals and 'Descripción' in vals:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("No se encontró la fila de cabecera de movimientos.")

    # 6) Tomar todo desde la siguiente fila
    data_df = df0.iloc[header_idx+2:].copy().reset_index(drop=True)

    # 7) Detener al encontrar la primera fila vacía
    def is_blank_row(r):
        # considera vacía si todas las celdas son NaN o cadenas vacías
        return all(pd.isna(v) or str(v).strip()=='' for v in r)
    blank_series = data_df.apply(is_blank_row, axis=1)
    if blank_series.any():
        first_blank = blank_series.idxmax()
        data_df = data_df.iloc[:first_blank]

    # 8) Extraer y limpiar encabezados
    raw_header = df0.iloc[header_idx].fillna('').astype(str).tolist()
    header = [h.strip() for h in raw_header]

    data_df.columns = header

    # 9) Renombrar columnas a nombres estándar
    ren = {
        'Fecha':        'fecha',
        'Referencia':   'referencia',
        'Descripción':  'descripcion',
        'Crédito (Q)':  'credito_gtq',
        'Débito (Q)':   'debito_gtq',
        'Crédito ($)':  'credito_usd',
        'Débito ($)':   'debito_usd'
    }
    df = data_df.rename(columns={k:v for k,v in ren.items() if k in data_df.columns})

    # 10) Normalizar y calcular montos
    df['fecha']       = pd.to_datetime(df['fecha'], dayfirst=True).dt.date
    df['referencia']  = df.get('referencia','').fillna('').astype(str).str.strip()
    df['descripcion'] = df.get('descripcion','').fillna('').astype(str).str.strip()

    for col in ('credito_gtq','debito_gtq','credito_usd','debito_usd'):
        if col in df:
            df[col] = pd.to_numeric(df[col].astype(str)
                                     .str.replace(r"[^\d\-\.]", "", regex=True),
                                     errors='coerce').fillna(0)
        else:
            df[col] = 0

    df['monto_gtq'] = df['credito_gtq'] - df['debito_gtq']
    df['monto_usd'] = df['credito_usd'] - df['debito_usd']
    # Usa GTQ si hay monto distinto de cero, sino USD
    df['monto']     = df['monto_gtq'].where(df['monto_gtq']!=0, df['monto_usd'])
    df['moneda']    = df['monto_gtq'].apply(lambda x: 'GTQ' if x!=0 else 'USD')

    # 11) Persistir movimientos
    for _, row in df.iterrows():
        mov = Movimiento(
            fecha=row['fecha'],
            descripcion=row['descripcion'],
            numero_documento=row['referencia'],
            monto=row['monto'],
            moneda=row['moneda'],
            tipo='debito' if row['monto'] < 0 else 'credito',
            cuenta_id=cuenta.id,
            archivo_id=archivo_obj.id
        )
        # Propagar propietario del archivo al movimiento
        if getattr(archivo_obj, 'user_id', None) is not None:
            mov.user_id = archivo_obj.user_id
        db.session.add(mov)
    db.session.commit()

    return len(df)
