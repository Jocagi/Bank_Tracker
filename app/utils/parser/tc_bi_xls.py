import pandas as pd
from datetime import datetime
import re
import logging
from ... import db
from ...models import Archivo, Movimiento, Cuenta
from ..classifier import clasificar_movimientos
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def _make_unique_headers(headers):
    unique = []
    seen = {}
    for raw in headers:
        base = (raw or '').strip().upper()
        if not base:
            base = 'UNNAMED'
        count = seen.get(base, 0)
        seen[base] = count + 1
        unique.append(base if count == 0 else f"{base}_{count + 1}")
    return unique


def _get_first_series(df, exact_names=None, contains_terms=None, default_value=''):
    exact_names = exact_names or []
    contains_terms = contains_terms or []

    for name in exact_names:
        if name in df.columns:
            col = df[name]
            return col.iloc[:, 0] if isinstance(col, pd.DataFrame) else col

    for col_name in df.columns:
        up = str(col_name).upper()
        if any(term in up for term in contains_terms):
            col = df[col_name]
            return col.iloc[:, 0] if isinstance(col, pd.DataFrame) else col

    return pd.Series([default_value] * len(df), index=df.index)

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
    # Normalizar y buscar de varias formas antes de crear para evitar violaciones UNIQUE
    numero_raw = (archivo_obj.numero_cuenta or '').strip()
    # forma limpia (solo alfanumérica) para comparaciones alternativas
    numero_clean = re.sub(r"[^A-Za-z0-9]", "", numero_raw)

    logger.debug("Buscando cuenta para banco=%r tipo=%r numero_raw=%r", archivo_obj.banco, archivo_obj.tipo_cuenta, numero_raw)
    # 1) Buscar por banco+tipo+numero tal como vienen
    cuenta = Cuenta.query.filter_by(
        banco=archivo_obj.banco,
        tipo_cuenta=archivo_obj.tipo_cuenta,
        numero_cuenta=numero_raw
    ).first()
    if cuenta:
        logger.debug("Cuenta encontrada por banco+tipo+numero: id=%r numero=%r", cuenta.id, cuenta.numero_cuenta)

    # 2) Si no se encontró, intentar buscar por numero exacto (porque la restricción UNIQUE puede ser sólo sobre numero_cuenta)
    if not cuenta and numero_raw:
        logger.debug("No encontrada por banco+tipo; buscando por numero_cuenta exacto: %r", numero_raw)
        cuenta = Cuenta.query.filter_by(numero_cuenta=numero_raw).first()
        if cuenta:
            logger.debug("Cuenta encontrada por numero_cuenta exacto: id=%r banco=%r tipo=%r", cuenta.id, cuenta.banco, cuenta.tipo_cuenta)

    # 3) Si aún no, buscar por la versión "limpia" (sin guiones/puntos/espacios)
    if not cuenta and numero_clean:
        logger.debug("Buscando por numero limpio (sin caracteres especiales): %r", numero_clean)
        # algunos registros pueden haberse guardado sin guiones; buscar equivalentes
        posibles = Cuenta.query.all()
        for c in posibles:
            if re.sub(r"[^A-Za-z0-9]", "", (c.numero_cuenta or '')) == numero_clean:
                cuenta = c
                logger.debug("Cuenta encontrada por numero limpio: id=%r numero=%r stored_clean=%r", c.id, c.numero_cuenta, re.sub(r"[^A-Za-z0-9]", "", (c.numero_cuenta or '')))
                break

    # 4) Si no existe, crear y proteger con try/except IntegrityError por si hay una carrera o registro concurrente
    if not cuenta:
        cuenta = Cuenta(
            banco=archivo_obj.banco,
            tipo_cuenta=archivo_obj.tipo_cuenta,
            numero_cuenta=numero_raw,
            titular=archivo_obj.titular,
            moneda=archivo_obj.moneda
        )
        # Asignar el usuario propietario del archivo a la cuenta
        if getattr(archivo_obj, 'user_id', None) is not None:
            cuenta.user_id = archivo_obj.user_id
        db.session.add(cuenta)
        try:
            db.session.commit()
            logger.debug("Cuenta creada: id=%r numero=%r", cuenta.id, cuenta.numero_cuenta)
        except IntegrityError as e:
            # Si otra transacción creó la cuenta entre nuestra búsqueda y el commit,
            # hacemos rollback y recuperamos la cuenta existente para continuar.
            logger.warning("IntegrityError al crear cuenta para numero=%r: %s", numero_raw, e)
            db.session.rollback()
            cuenta = None
            if numero_raw:
                cuenta = Cuenta.query.filter_by(numero_cuenta=numero_raw).first()
                if cuenta:
                    logger.debug("Recuperada cuenta después de IntegrityError por numero_raw: id=%r numero=%r", cuenta.id, cuenta.numero_cuenta)
            if not cuenta:
                # último recurso: buscar por versión limpia
                if numero_clean:
                    posibles = Cuenta.query.all()
                    for c in posibles:
                        if re.sub(r"[^A-Za-z0-9]", "", (c.numero_cuenta or '')) == numero_clean:
                            cuenta = c
                            logger.debug("Recuperada cuenta después de IntegrityError por numero_clean: id=%r numero=%r", c.id, c.numero_cuenta)
                            break
            if not cuenta:
                # Si todavía no hay cuenta, re-raise para que el error sea visible
                logger.error("No se pudo recuperar o crear la cuenta tras IntegrityError para numero=%r", numero_raw)
                raise

    # 4) Detectar dinámicamente la fila de cabecera real de movimientos
    # Evita falsos positivos en metadatos como "FECHA DE PAGO".
    header_idx = None
    for i in range(len(df0)):
        row_vals = [str(v).strip().upper() for v in df0.iloc[i].fillna('').astype(str).tolist()]
        has_fecha = any(v == 'FECHA' or 'FECHA' in v for v in row_vals)
        header_hints = sum(
            1 for v in row_vals
            if any(token in v for token in ('MOVIMIENTO', 'MOVMIENTO', 'DOC', 'COMERCIO', 'VALOR', 'SALDO'))
        )
        if has_fecha and header_hints >= 2:
            header_idx = i
            break

    # Fallback si no encontramos la cabecera: usar índice tradicional (línea 13 -> índice 12)
    if header_idx is None:
        header_idx = 12

    if len(df0) <= header_idx:
        raise ValueError(f"El archivo tiene menos de {header_idx+1} filas, no se puede leer la cabecera de movimientos.")

    # Tomar cabecera y normalizar nombres (strip + upper) para facilitar mapeo
    header = df0.iloc[header_idx].fillna('').astype(str).tolist()
    header_norm = _make_unique_headers(header)

    # 5) Construir DataFrame de movimientos desde la fila siguiente a la cabecera
    movs = df0.iloc[header_idx+1:].copy().reset_index(drop=True)
    movs.columns = header_norm

    # 6) Detener en la primera fila completamente vacía
    blank = movs.apply(lambda r: all(str(v).strip()=='' for v in r), axis=1)
    if blank.any():
        movs = movs.loc[:blank.idxmax()-1]

    # 7) Extraer columnas de forma segura a nombres estándar
    fecha_src = _get_first_series(movs, exact_names=['FECHA'], contains_terms=['FECHA'])
    tipo_src = _get_first_series(
        movs,
        exact_names=['TIPO DE MOVIMIENTO', 'TIPO DE MOVMIENTO'],
        contains_terms=['TIPO DE MOVIMIENTO', 'TIPO DE MOVMIENTO', 'TIPO']
    )
    documento_src = _get_first_series(
        movs,
        exact_names=['NO. DOC', 'NO. DOCUMENTO'],
        contains_terms=['NO. DOC', 'DOCUMENTO', 'DOC']
    )
    descripcion_src = _get_first_series(
        movs,
        exact_names=['COMERCIO', 'DESCRIPCION'],
        contains_terms=['COMERCIO', 'DESCRIPCION']
    )
    monto_src = _get_first_series(movs, exact_names=['VALOR', 'MONTO'], contains_terms=['VALOR', 'MONTO'])

    movs = pd.DataFrame({
        'fecha': fecha_src,
        'tipo': tipo_src,
        'numero_documento': documento_src,
        'descripcion': descripcion_src,
        'monto': monto_src,
    }, index=movs.index)

    # 8) Normalizar datos y calcular monto
    movs['fecha'] = pd.to_datetime(movs['fecha'], dayfirst=True, errors='coerce').dt.date
    movs['tipo'] = movs['tipo'].astype(str).str.strip()
    movs['descripcion'] = movs['descripcion'].astype(str).str.strip()
    movs['numero_documento'] = movs['numero_documento'].astype(str).str.strip()

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

    # Remueve filas sin fecha o sin monto
    movs = movs.dropna(subset=['fecha', 'monto'])

    movs['monto'] = movs.apply(
        lambda row: -row['monto']
        if row['tipo'].upper() in ('DEBITO', 'CONSUMO')
        else row['monto'],
        axis=1
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
        # Propagar propietario del archivo al movimiento
        if getattr(archivo_obj, 'user_id', None) is not None:
            m.user_id = archivo_obj.user_id
        db.session.add(m)
        count += 1
    db.session.commit()

    return count
