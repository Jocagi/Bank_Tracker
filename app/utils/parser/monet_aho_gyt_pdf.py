import re
import pdfplumber
import pandas as pd

from ... import db
from ...models import Movimiento, Cuenta

def load_movements_monet_aho_gyt_pdf(filepath, archivo_obj):
    """
    Lee el PDF de estado de cuenta GYT (monet-aho-gyt):
    1) Extrae y parsea el encabezado (primeras ~8 líneas).
    2) Extrae la tabla de movimientos de cada página con pdfplumber.
    3) Concatena, renombra "Crédito/Débito" a 'monto', normaliza y guarda cada Movimiento en la BD.
    Retorna el número de movimientos agregados.
    """
    # --- 1) Extraer líneas completas para el encabezado ---
    with pdfplumber.open(filepath) as pdf:
        lines = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(text.split('\n'))

    header_info = {}
    for line in lines[:8]:
        if 'Nombre cuenta:' in line:
            header_info['titular'] = line.split('Nombre cuenta:', 1)[1].strip()
        elif 'Cuenta:' in line:
            # Ej: "Cuenta: MONETARIO QTZ. 34-38089-1"
            parts = line.split('Cuenta:', 1)[1].strip().split()
            header_info['tipo_cuenta']   = parts[0].upper()
            header_info['moneda']        = parts[1].strip('().').upper()
            header_info['numero_cuenta'] = parts[-1]
        elif 'Saldo inicial' in line:
            m = re.search(r'Saldo inicial\s+([\d,\.]+)', line)
            if m:
                header_info['saldo'] = float(m.group(1).replace(',', ''))

    # --- 2) Estandarizar abreviaturas ---
    if header_info.get('moneda') == 'QTZ':
        header_info['moneda'] = 'GTQ'
    tc = header_info.get('tipo_cuenta', '').upper()
    if tc == 'MONETARIO':
        header_info['tipo_cuenta'] = 'MONET'
    elif tc == 'AHORRO':
        header_info['tipo_cuenta'] = 'AHO'

    # --- 3) Actualizar metadatos en Archivo ---
    archivo_obj.tipo_cuenta   = header_info.get('tipo_cuenta', 'Desconocido')
    archivo_obj.moneda        = header_info.get('moneda', 'Desconocido')
    archivo_obj.numero_cuenta = header_info.get('numero_cuenta', 'Desconocido')
    archivo_obj.titular       = header_info.get('titular', 'Desconocido')
    archivo_obj.saldo_inicial = header_info.get('saldo', 0.0)
    db.session.commit()

    # --- 4) Verificar o crear Cuenta ---
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

    # --- 5) Extraer y concatenar todas las tablas de movimientos ---
    tables = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            tbl = page.extract_table({
                "vertical_strategy":   "lines",
                "horizontal_strategy": "lines"
            })
            if tbl and len(tbl) > 1:
                tables.append(pd.DataFrame(tbl[1:], columns=tbl[0]))

    if not tables:
        raise ValueError("No se detectó la tabla de movimientos en el PDF.")

    # Unir todas las páginas
    df = pd.concat(tables, ignore_index=True)

    # --- 6) Renombrar columnas según tu formato ---
    df = df.rename(columns={
        "Fecha":           "fecha",
        "Doc":             "documento",
        "Descripción":     "descripcion",
        "Lugar":           "lugar",
        "Crédito/Débito":  "monto",
        "Saldo":           "saldo"
    })

    # --- 7) Normalizar datos ---
    df["fecha"]    = pd.to_datetime(df["fecha"], dayfirst=True).dt.date
    df["saldo"]    = (
        df["saldo"]
        .str.replace(r"[^\d\-\.]", "", regex=True)
        .replace("", "0")
        .astype(float)
    )
    df["monto"]    = (
        df["monto"]
        .str.replace(r"[^\d\-\.]", "", regex=True)
        .replace("", "0")
        .astype(float)
    )
    df["moneda"]   = archivo_obj.moneda
    df["descripcion"] = df["descripcion"].fillna("")
    df["lugar"]       = df["lugar"].fillna("")
    df["documento"]   = df["documento"].fillna("")

    # --- 8) Insertar cada movimiento en la BD ---
    for _, row in df.iterrows():
        mov = Movimiento(
            fecha=row["fecha"],
            descripcion=row["descripcion"],
            lugar=row["lugar"],
            numero_documento=row["documento"],
            monto=row["monto"],
            moneda=row["moneda"],
            tipo="debito" if row["monto"] < 0 else "credito",
            cuenta_id=cuenta.id,
            archivo_id=archivo_obj.id
        )
        db.session.add(mov)
    db.session.commit()

    return len(df)
