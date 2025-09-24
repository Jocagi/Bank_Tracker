
import pdfplumber
import pandas as pd

from ... import db
from ...models import Movimiento, Cuenta

def load_movements_tc_gyt_pdf(filepath, archivo_obj):
    """
    Lee el PDF de estado de cuenta GYT (tarjeta de crédito):
    1) Extrae y parsea el encabezado (primeras ~2 líneas).
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
        # Ej. "Nombre cuenta: JOSE GIRON 09-07-2025 | 07:18:06"
        if 'Nombre cuenta:' in line:
            owner = line.split('Nombre cuenta:', 1)[1].strip().split('|')[0].strip().split(' ')[0:-1]
            header_info['titular'] = ' '.join(owner) if owner else 'Desconocido'
        elif 'Cuenta:' in line:
            # Ej: "Cuenta: TCR 5522-****-****-8241 Día de corte 09 | Día de pago: 04"
            parts = line.split('Cuenta:', 1)[1].strip().split('|')
            header_info['numero_cuenta'] = parts[0].strip().split()[-5] if parts else 'Desconocido'
            header_info['tipo_cuenta']   = 'TC'
            header_info['moneda']        = 'GTQ|USD'
            break

    # --- 3) Actualizar metadatos en Archivo ---
    archivo_obj.tipo_cuenta   = header_info.get('tipo_cuenta', 'Desconocido')
    archivo_obj.moneda        = header_info.get('moneda', 'Desconocido')
    archivo_obj.numero_cuenta = header_info.get('numero_cuenta', 'Desconocido')
    archivo_obj.titular       = header_info.get('titular', 'Desconocido')
    db.session.commit()

    # --- 3) Verificar o crear Cuenta ---
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

    # --- 4) Extraer y concatenar tablas de todas las páginas ---
    tablas = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            tbl = page.extract_table({
                "vertical_strategy":   "lines",
                "horizontal_strategy": "lines"
            })
            if tbl:
                # Eliminar filas encabezado y agregar uno personalizado
                if page.page_number == 1:
                    # Validar si en la segunda línea está el texto "Cuenta: TCR"
                    if 'Cuenta:' in lines[6]:
                        # Eliminar encabezado de página
                        tbl = [tbl[0]] + tbl[2:]
                    else:
                        # Eliminar solo la primera fila
                        tbl = [tbl[0]] + tbl[1:]
                elif page.page_number > 1:
                    tbl = [tbl[0]] + tbl[1:]
                tbl[0] = ['fecha', 'documento', 'blank1', 'descripcion', 'blank2', 'blank3', 'raw_monto', 'blank4', 'blank5']
                # Convertir a DataFrame y agregar a la lista
                df = pd.DataFrame(tbl[1:], columns=tbl[0])
                tablas.append(df)

    if not tablas:
        raise ValueError("No se detectó la tabla de movimientos en el PDF.")

    df = pd.concat(tablas, ignore_index=True)

    # --- 7) Normalizar datos ---
    df['fecha'] = pd.to_datetime(
        df['fecha'], dayfirst=True, errors='coerce'
    ).dt.date

    df['documento']   = df['documento'].fillna('').astype(str).str.strip()
    df['descripcion'] = df['descripcion'].fillna('').astype(str).str.strip()

    # Extraer moneda
    df['moneda'] = (
        df['raw_monto']
          .fillna('')
          .astype(str)
          .str.extract(r'\b(QTZ)\b', expand=False)
          .map({'QTZ':'GTQ'})
          .fillna('USD')
    )
    # Limpiar y convertir monto numérico
    df['monto'] = (
        df['raw_monto']
          .fillna('')
          .astype(str)
          .str.replace(r'[^\d\-\.\,]', '', regex=True)
          .str.replace(',', '', regex=False)
          .replace('', '0')
          .astype(float)
    )

    # --- 8) Omitir filas sin fecha y sin referencia ---
    df = df[
        df['fecha'].notna() |
        df['documento'].astype(bool)
    ]

    # --- 9) Persistir cada movimiento ---
    for _, row in df.iterrows():
        mov = Movimiento(
            fecha=row['fecha'],
            descripcion=row['descripcion'],
            numero_documento=row['documento'],
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
