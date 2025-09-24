import re
import pdfplumber
from datetime import datetime
from ... import db
from ...models import Archivo, Movimiento, Cuenta
from ..classifier import clasificar_movimientos

def load_movements_bi_monet_pdf(filepath, archivo_obj):
    """
    Parser para estado de cuenta monetaria del Banco Industrial (PDF):
      1) Extrae encabezado y metadata (titular, cuenta, mes).
      2) Extrae el SALDO ANTERIOR.
      3) Lee cada línea de movimiento:
         - Fecha, documento, descripción, monto, saldo.
         - Detecta moneda por sufijo en descripción (GT → GTQ, US → USD).
         - Determina tipo (débito/crédito) comparando saldo con el anterior.
      4) Persiste movimientos y clasificarlos.
    Devuelve el número de movimientos agregados.
    """
    # --- 1) Extraer texto por líneas ---
    with pdfplumber.open(filepath) as pdf:
        lines = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(text.split('\n'))

    # --- 2) Metadata de cuenta ---
    header_info = {}
    for line in lines[:10]:
        if 'Número de cuenta:' in line:
            # "Número de cuenta: 1850074608  Correspondiente al mes de: junio 2025"
            parts = re.split(r'Número de cuenta:|Correspondiente al mes de:', line)
            if len(parts) >= 3:
                header_info['numero_cuenta'] = parts[1].strip()
                # Mes actual (no se usa en BD)
    archivo_obj.banco        = 'BI'
    archivo_obj.tipo_cuenta  = 'MONET'
    archivo_obj.numero_cuenta = header_info.get('numero_cuenta', 'Desconocido')
    archivo_obj.titular      = lines[2].strip() if len(lines) > 1 else 'Desconocido'
    archivo_obj.moneda       = 'GTQ'
    db.session.commit()

    # --- 3) Crear o recuperar cuenta ---
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

    # --- 4) Buscar SALDO ANTERIOR ---
    prev_balance = None
    for line in lines:
        m = re.match(r'^\*+SALDO ANTERIOR\*+\s*([\d,\.]+)$', line.strip())
        if m:
            prev_balance = float(m.group(1).replace(',', ''))
            break

    # --- 5) Procesar cada línea de transacción ---
    tx_pattern = re.compile(
        r'^(?P<fecha>\d{2}\/\d{2}\/\d{4})\s+'
        r'(?P<doc>\d+)\s+'
        r'(?P<desc>.+?)\s+'
        r'(?P<monto>[\d,\.]+)\s*'
        r'(?P<saldo>[\d,\.]*)$'
    )
    count = 0
    for line in lines:
        line = line.strip()
        m = tx_pattern.match(line)
        if not m or prev_balance is None:
            continue

        # Campos extraídos
        fecha = datetime.strptime(m.group('fecha'), '%d/%m/%Y').date()
        doc   = m.group('doc')
        desc  = m.group('desc').strip()
        amt   = float(m.group('monto').replace(',', ''))
        bal   = float(m.group('saldo').replace(',', '')) if m.group('saldo') else 0.0

        # Valor por defecto para moneda
        moneda = 'GTQ'

        # Determinar tipo comparando con el saldo anterior
        tipo = 'credito' if bal > prev_balance else 'debito'
        prev_balance = bal

        # Crear movimiento
        mov = Movimiento(
            fecha=fecha,
            descripcion=desc,
            lugar=None,
            numero_documento=doc,
            monto=amt if tipo=='credito' else -amt,
            moneda=moneda,
            tipo=tipo,
            cuenta_id=cuenta.id,
            archivo_id=archivo_obj.id
        )
        # Propagar propietario del archivo al movimiento
        if getattr(archivo_obj, 'user_id', None) is not None:
            mov.user_id = archivo_obj.user_id
        db.session.add(mov)
        count += 1

    db.session.commit()

    # --- 6) Clasificar movimientos nuevos ---
    clasificar_movimientos()

    return count
