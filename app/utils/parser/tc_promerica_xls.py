import pandas as pd
from ... import db
from ...models import Movimiento, Cuenta

def load_movements_promerica_tc_xls(filepath, archivo_obj):
    """
    Parser para estado de cuenta de Tarjeta de Crédito Promerica (en formato HTML),
    asumiendo que la tabla de movimientos arranca en la línea 22 (índice 22):
      1) Extrae metadata de las primeras filas.
      2) Actualiza archivo_obj y crea/recupera Cuenta.
      3) Toma la fila 22 como cabecera de movimientos.
      4) Lee desde línea 23 hasta la primera línea vacía.
      5) Renombra, normaliza y persiste Movimientos.
      6) Reclasifica automáticamente.
    Retorna el número de movimientos agregados.
    """
    # 1) Leer toda la hoja 0 como strings
    df0 = pd.read_html(filepath)

    # 2) Extraer metadata
    titular = str(df0[3].iloc[1, 1]).strip() if pd.notna(df0[3].iloc[1, 1]) else ''
    numero = str(df0[3].iloc[2, 3]).strip() if pd.notna(df0[3].iloc[2, 1]) else ''
    if '-' in numero:
        numero = numero.split('-')[0].strip()

    moneda = 'GTQ|USD'
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
        # Asignar el usuario propietario del archivo a la cuenta
        if getattr(archivo_obj, 'user_id', None) is not None:
            cuenta.user_id = archivo_obj.user_id
        db.session.add(cuenta)
        db.session.commit()

    # 4) Tomar el séptimo valor del dataframe como la tabla de movimientos
    if len(df0) < 7:
        raise ValueError("El archivo no contiene suficientes hojas para extraer movimientos.")
    df_movs = df0[6]
    if df_movs.empty:
        raise ValueError("No se encontraron movimientos en la hoja esperada.")
    header = df_movs.iloc[0].astype(str).str.strip().tolist()

    # 5) Construir DataFrame de movimientos
    movs = df_movs.iloc[1:].copy().reset_index(drop=True)
    movs.columns = header

    # 6) Renombrar columnas a nombres estándar
    ren = {
        'Fecha de Operación': 'fecha',
        'Descripción': 'descripcion',
        'Débitos': 'debito',
        'Créditos': 'credito',
        'Número de Referencia': 'documento',
        'Moneda': 'moneda'
    }
    cols = {k: v for k, v in ren.items() if k in movs.columns}
    movs = movs.rename(columns=cols)

    # 8) Normalizar datos y calcular monto
    movs['fecha']       = pd.to_datetime(movs['fecha'], dayfirst=True, errors='coerce').dt.date
    movs['descripcion'] = movs['descripcion'].astype(str).str.strip()
    movs['numero_documento'] = movs.get('documento', '').astype(str).str.strip()    
    # convertir montos a numéricos, manejando errores
    movs['debito'] = pd.to_numeric(movs['debito'], errors='coerce').fillna(0)
    movs['credito'] = pd.to_numeric(movs['credito'], errors='coerce').fillna(0)
    movs['monto']  = movs['credito'] - movs['debito']
    movs['moneda'] = movs['moneda'].str.strip().str.upper()
    movs['moneda'] = movs['moneda'].replace({'QUETZALES': 'GTQ', 'DOLARES': 'USD'})

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
        # Propagar propietario del archivo al movimiento
        if getattr(archivo_obj, 'user_id', None) is not None:
            m.user_id = archivo_obj.user_id
        db.session.add(m)
        count += 1
    db.session.commit()

    return count
