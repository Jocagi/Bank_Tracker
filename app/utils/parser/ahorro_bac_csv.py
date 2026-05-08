import csv
from datetime import datetime

from ... import db
from ...models import Movimiento
from .cuenta_utils import get_or_create_cuenta


def _parse_float(value):
    s = (value or '').strip()
    if not s:
        return 0.0
    s = s.replace(',', '')
    try:
        return float(s)
    except Exception:
        return 0.0


def _parse_date(value):
    s = (value or '').strip()
    if not s:
        return None
    for fmt in ('%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _read_csv_rows(filepath):
    # BAC exporta con codificación variable (latin-1/cp1252/utf-8)
    for enc in ('utf-8-sig', 'latin-1', 'cp1252'):
        try:
            with open(filepath, 'r', encoding=enc, newline='') as f:
                return list(csv.reader(f, skipinitialspace=True))
        except UnicodeDecodeError:
            continue
    with open(filepath, 'r', encoding='latin-1', newline='') as f:
        return list(csv.reader(f, skipinitialspace=True))


def _norm(text):
    return (text or '').strip().lower()


def load_movements_ahorro_bac_csv(filepath, archivo_obj):
    """
    Parser para cuentas de ahorro BAC (.csv).
    Espera un layout con:
    - Bloque de metadatos (cliente, producto, moneda, saldo inicial/libros)
    - Sección "Detalle de Estado Bancario" con columnas de débito/crédito.
    """
    rows = _read_csv_rows(filepath)
    if len(rows) < 2:
        raise ValueError('CSV BAC inválido o vacío.')

    header = rows[0]
    values = rows[1] if len(rows) > 1 else []
    meta = {}
    for idx, key in enumerate(header):
        if idx < len(values):
            meta[_norm(key)] = (values[idx] or '').strip()

    titular = meta.get('nombre') or meta.get(' name') or ''
    numero_cuenta = meta.get('producto') or ''
    moneda_raw = meta.get('moneda') or ''
    moneda = 'GTQ' if moneda_raw.upper() in ('QTZ', 'GTQ', 'Q') else (moneda_raw.upper() or 'GTQ')
    saldo_inicial = _parse_float(meta.get('saldo inicial'))
    saldo_libros = _parse_float(meta.get('saldo en libros'))

    archivo_obj.tipo_cuenta = 'AHO'
    archivo_obj.numero_cuenta = numero_cuenta or 'BAC-AHORRO'
    archivo_obj.titular = titular or getattr(archivo_obj, 'titular', 'Desconocido')
    archivo_obj.moneda = moneda
    archivo_obj.saldo_inicial = saldo_inicial
    db.session.commit()

    cuenta = get_or_create_cuenta(archivo_obj, preferred_tipo='AHO', create=True)
    if not cuenta:
        raise ValueError('No se pudo localizar/crear la cuenta BAC ahorro.')

    # Buscar inicio de sección detalle
    detalle_idx = None
    for i, row in enumerate(rows):
        joined = ' '.join(row).lower()
        if 'detalle de estado bancario' in joined:
            detalle_idx = i
            break

    if detalle_idx is None or detalle_idx + 1 >= len(rows):
        raise ValueError('No se encontró la sección "Detalle de Estado Bancario".')

    # Header de detalle
    det_header = rows[detalle_idx + 1]
    idx_map = {}
    for i, col in enumerate(det_header):
        c = _norm(col)
        if 'fecha' in c:
            idx_map['fecha'] = i
        elif 'referencia' in c:
            idx_map['ref'] = i
        elif 'descripci' in c:
            idx_map['desc'] = i
        elif 'débito' in c or 'debito' in c:
            idx_map['debito'] = i
        elif 'crédito' in c or 'credito' in c:
            idx_map['credito'] = i
        elif 'balance' in c:
            idx_map['balance'] = i

    required = ('fecha', 'desc', 'debito', 'credito')
    for k in required:
        if k not in idx_map:
            raise ValueError(f'Columna requerida no encontrada en detalle BAC: {k}')

    movimientos = []
    for row in rows[detalle_idx + 2:]:
        joined = ' '.join(row).strip().lower()
        if not joined:
            continue
        if 'resumen de estado bancario' in joined:
            break

        fecha = _parse_date(row[idx_map['fecha']] if idx_map['fecha'] < len(row) else '')
        if not fecha:
            continue

        descripcion = (row[idx_map['desc']] if idx_map['desc'] < len(row) else '').strip()
        referencia = (row[idx_map['ref']] if 'ref' in idx_map and idx_map['ref'] < len(row) else '').strip()

        debito = _parse_float(row[idx_map['debito']] if idx_map['debito'] < len(row) else '')
        credito = _parse_float(row[idx_map['credito']] if idx_map['credito'] < len(row) else '')

        if debito == 0 and credito == 0:
            continue

        if debito > 0:
            monto = -debito
            tipo = 'debito'
        else:
            monto = credito
            tipo = 'credito'

        movimientos.append({
            'fecha': fecha,
            'descripcion': descripcion,
            'numero_documento': referencia,
            'monto': monto,
            'tipo': tipo,
        })

    for mov in movimientos:
        m = Movimiento(
            fecha=mov['fecha'],
            cuenta_id=cuenta.id,
            descripcion=mov['descripcion'],
            numero_documento=mov['numero_documento'],
            monto=mov['monto'],
            moneda=moneda,
            tipo=mov['tipo'],
            archivo_id=archivo_obj.id,
        )
        if getattr(archivo_obj, 'user_id', None) is not None:
            m.user_id = archivo_obj.user_id
        db.session.add(m)

    # Saldo final de cuenta por balance final o saldo en libros
    if movimientos:
        # intentamos usar último balance de detalle si existe
        if 'balance' in idx_map:
            last_balance = None
            for row in rows[detalle_idx + 2:]:
                joined = ' '.join(row).strip().lower()
                if 'resumen de estado bancario' in joined:
                    break
                if idx_map['balance'] < len(row):
                    val = _parse_float(row[idx_map['balance']])
                    if val != 0 or (row[idx_map['balance']] or '').strip() in ('0', '0.00'):
                        last_balance = val
            if last_balance is not None:
                cuenta.saldo = last_balance
            else:
                cuenta.saldo = saldo_libros
        else:
            cuenta.saldo = saldo_libros
        db.session.add(cuenta)

    db.session.commit()
    return len(movimientos)
