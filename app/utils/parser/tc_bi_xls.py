import pandas as pd
from datetime import datetime
from ... import db
from ...models import Archivo, Movimiento, Cuenta
from ..classifier import clasificar_movimientos

def load_movements_bi_tc_xls(filepath, archivo_obj):
    """
    Parser para estado de cuenta de Tarjeta de Crédito BI (.xls),
    asumiendo que la tabla de movimientos arranca en la línea 13 (índice 12):
      1) Extrae metadata de las primeras filas.
      2) Actualiza archivo_obj y crea/recupera Cuenta.
      3) Toma la fila 13 como cabecera de movimientos.
      4) Lee desde línea 14 hasta la primera línea vacía.
      5) Renombra, normaliza y persiste Movimientos.
      6) Reclasifica automáticamente.
    Retorna el número de movimientos agregados.
    """
    # 1) Leer toda la hoja 0 como strings
    df0 = pd.read_excel(filepath, sheet_name=0, header=None, dtype=str)

    # Helper para evitar NoneType.strip()
    def safe_str(val):
        return str(val).strip() if pd.notna(val) else ''

    # 2) Extraer metadata (igual que antes)
    titular = safe_str(df0.iloc[2, 1]) if len(df0) > 2 else archivo_obj.titular
    numero  = safe_str(df0.iloc[4, 1]) if len(df0) > 4 else archivo_obj.numero_cuenta
    mcell   = safe_str(df0.iloc[6, 1]) if len(df0) > 6 else ''
    moneda  = 'USD' if ('$' in mcell or 'USD' in mcell.upper()) else 'GTQ'

    archivo_obj.tipo_cuenta   = 'TC'
    archivo_obj.numero_cuenta = numero
    archivo_obj.titular       = titular
    archivo_obj.moneda        = moneda
    db.session.commit()

    # 3) Crear o recuperar Cuenta
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

    # 4) Tomar línea 12 como cabecera (índice 11)
    header_idx = 11
    if len(df0) <= header_idx:
        raise ValueError(f"El archivo tiene menos de {header_idx+1} filas, no se puede leer la cabecera de movimientos.")
    header = df0.iloc[header_idx].fillna('').astype(str).tolist()

    # 5) Construir DataFrame de movimientos desde línea 14 (índice 13)
    movs = df0.iloc[header_idx+1:].copy().reset_index(drop=True)
    movs.columns = header

    # 6) Detener en la primera fila completamente vacía
    blank = movs.apply(lambda r: all(str(v).strip()=='' for v in r), axis=1)
    if blank.any():
        movs = movs.loc[:blank.idxmax()-1]

    # 7) Renombrar columnas a nombres estándar
    ren = {
        'FECHA':       'fecha',
        'TIPO DE MOVMIENTO': 'tipo',
        'NO. DOC':     'documento',
        'COMERCIO':    'descripcion',
        'VALOR':       'monto',
    }
    cols = {k: v for k, v in ren.items() if k in movs.columns}
    movs = movs.rename(columns=cols)

    # 8) Normalizar datos y calcular monto
    movs['fecha']       = pd.to_datetime(movs['fecha'], dayfirst=True, errors='coerce').dt.date
    movs['descripcion'] = movs['descripcion'].astype(str).str.strip()
    movs['numero_documento'] = movs.get('documento', '').astype(str).str.strip()

    # Convertir columnas de monto a numéricas, manejando errores y formatos
    # Tiene símbolo de moneda
    # Ej. "Q. 7,400.40" o "$. 1,200.00"
    def parse_monto(val):
        if pd.isna(val):
            return 0.0
        val = str(val).replace('Q.', '').replace('$.', '').replace(',', '')
        try:
            return float(val.strip())
        except ValueError:
            return 0.0
    
    movs['monto'] = movs['monto'].apply(parse_monto)

    # Debug imprime cada columna renombrada y su contenido
    for col in movs.columns:
        print(f"Columna '{col}': \n{movs[col]}")

    # Remueve filas sin fecha o sin monto
    movs = movs.dropna(subset=['fecha', 'monto'])

    movs['monto']  = movs.apply(
        lambda row: -row['monto'] 
        if row['tipo'].strip().upper() == 'DEBITO' or row['tipo'].strip().upper() == 'CONSUMO'
        else row['monto'], axis=1
    )
    movs['moneda'] = archivo_obj.moneda

    # 9) Persistir movimientos
    count = 0
    for _, row in movs.iterrows():
        if pd.isna(row['fecha']):
            continue
        m = Movimiento(
            fecha=row['fecha'],
            descripcion=row['descripcion'],
            numero_documento=row['numero_documento'],
            monto=row['monto'],
            moneda=row['moneda'],
            tipo='debito' if row['monto'] < 0 else 'credito',
            cuenta_id=cuenta.id,
            archivo_id=archivo_obj.id
        )
        db.session.add(m)
        count += 1
    db.session.commit()

    return count
