import re
import pdfplumber
from datetime import datetime
from ... import db
from ...models import Archivo, Movimiento, Cuenta
from ..classifier import clasificar_movimientos

def load_movements_bi_tc_email_pdf(filepath, archivo_obj):
    """
    Parser para estado de cuenta de tarjeta de crédito del Banco Industrial (PDF enviado por email):
      1) Extrae encabezado y metadata (titular, cuenta, fecha de corte).
      2) Lee movimientos en quetzales y dólares por separado.
      3) Usa la fecha de consumo en lugar de la fecha de operación.
      4) Determina débitos y créditos basándose en las columnas correspondientes.
      5) Persiste movimientos y los clasifica.
    Devuelve el número de movimientos agregados.
    """
    # --- 1) Extraer texto por líneas ---
    with pdfplumber.open(filepath) as pdf:
        lines = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(text.split('\n'))

    # --- 2) Metadata de cuenta ---
    titular = 'Desconocido'
    numero_cuenta = 'Desconocido'
    categoria_tarjeta = 'TC'  # Siempre "TC" (sin categoría)
    categoria_detectada = None  # p.ej. PLATINUM, CLASICA
    ultimos_digitos = None
    fecha_corte = None
    
    # Buscar información de cuenta en las primeras líneas (ampliamos el rango por variaciones en PDFs)
    # Acepta separadores variables entre bloques ("XXXX XXXX XXXX 9601", "XXXX-XXXX-XXXX-9601", "XXXX - XXXX - XXXX - 9601")
    # y opcionalmente una categoría textual (p.ej. "PLATINUM", "Clasica") después.
    card_pattern = re.compile(
        r'XXXX(?:[\s-]+XXXX){2}[\s-]+(\d{4})(?:\s+([A-Za-zÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑ\- ]*))?',
        re.IGNORECASE
    )
    for i, line in enumerate(lines[:80]):
        raw = line.strip()
        # Buscar titular (heurística: línea mayúsculas, longitud razonable, sin palabras de dirección)
        if i < 15 and re.match(r'^[A-ZÁÉÍÓÚÑ\s]+$', raw) and 10 < len(raw) < 60:
            if not any(token in raw for token in ['GUATEMALA', 'ZONA', 'CALLE']):
                titular = raw

        # Buscar número de tarjeta en formatos: "XXXX XXXX XXXX 9601 PLATINUM" o "XXXX-XXXX-XXXX-9601 Platinum" o sin categoría
        m_card = card_pattern.search(raw)
        if m_card:
            ultimos_digitos = m_card.group(1)
            cat_raw = m_card.group(2)
            categoria_detectada = (cat_raw.split()[0] if cat_raw else None)
            if categoria_detectada:
                categoria_detectada = categoria_detectada.upper()
            numero_cuenta = f"XXXX-XXXX-XXXX-{ultimos_digitos}"
            # Mantener tipo de cuenta como "TC" únicamente
            categoria_tarjeta = 'TC'

        # Buscar fecha de corte: puede venir con espacios o con barras
        if 'Fecha de corte:' in raw:
            match = re.search(r'Fecha de corte:\s*(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})', raw)
            if match:
                dia, mes, año = match.groups()
                try:
                    año_int = int(año)
                    if len(año) == 2:  # Ajuste año 2 dígitos
                        año_int += 2000 if año_int <= 50 else 1900
                    fecha_corte = datetime(año_int, int(mes), int(dia)).date()
                except ValueError:
                    fecha_corte = None

    archivo_obj.banco = 'BI'
    # Guardar en Archivo sólo "TC" como tipo de cuenta
    archivo_obj.tipo_cuenta = 'TC'
    archivo_obj.numero_cuenta = numero_cuenta
    archivo_obj.titular = titular
    archivo_obj.moneda = 'GTQ|USD'  # Reporta ambas monedas separadas por |
    db.session.commit()

    # --- 3) Crear o recuperar cuenta ---
    # Intentar localizar cuenta por número, incluyendo números alternativos
    cuenta = Cuenta.find_by_numero(archivo_obj.numero_cuenta)

    # Asegurar que la cuenta encontrada corresponde al mismo banco y tipo (p. ej. TC)
    if cuenta:
        try:
            if cuenta.banco != archivo_obj.banco or not cuenta.tipo_cuenta.startswith(archivo_obj.tipo_cuenta):
                # Si no coincide, descartamos esta coincidencia para buscar una que sí coincida con banco/tipo
                cuenta = None
        except Exception:
            cuenta = None

    # Si aún no hay cuenta, buscar también sin guiones por si existe en otro formato dentro del mismo banco/tipo
    if not cuenta:
        numero_sin_guiones = numero_cuenta.replace('-', '')
        # Buscar cuentas del mismo banco y con tipos de TC similares que contengan los mismos dígitos
        cuentas_similares = Cuenta.query.filter(
            Cuenta.banco == archivo_obj.banco,
            Cuenta.tipo_cuenta.like('TC%')  # Cualquier tipo que empiece con TC
        ).all()

        for cuenta_existente in cuentas_similares:
            if cuenta_existente.numero_cuenta.replace('-', '') == numero_sin_guiones:
                cuenta = cuenta_existente
                break
    
    if not cuenta:
        # Si es cuenta nueva, forzar tipo_cuenta = "TC" y, si hay categoría, colocarla en el alias
        alias_sugerido = None
        if categoria_detectada and ultimos_digitos:
            alias_sugerido = f"{categoria_detectada} {ultimos_digitos}"

        cuenta = Cuenta(
            banco=archivo_obj.banco,
            tipo_cuenta='TC',
            numero_cuenta=archivo_obj.numero_cuenta,
            alias=alias_sugerido,
            titular=archivo_obj.titular,
            moneda=archivo_obj.moneda
        )
        # Asignar el usuario propietario del archivo a la cuenta
        if getattr(archivo_obj, 'user_id', None) is not None:
            cuenta.user_id = archivo_obj.user_id
        db.session.add(cuenta)
        db.session.commit()

    # --- 4) Procesar movimientos ---
    count = 0
    current_currency = None
    in_movements_section = False
    current_section_type = None  # Para distinguir entre MOVIMIENTOS, OTROS CARGOS, OTROS CREDITOS
    stop_processing = False  # Flag para parar después de PAGOS REALIZADOS
    
    for line in lines:
        line = line.strip()
        
        # Si encontramos PAGOS REALIZADOS o BALANCE DE INTERESES, parar de procesar
        if 'PAGOS REALIZADOS' in line or 'BALANCE DE INTERESES' in line:
            stop_processing = True
            break
        
        # Si ya paramos de procesar, no continuar
        if stop_processing:
            break
        
        # Detectar secciones principales
        if 'OTROS CARGOS' in line:
            current_section_type = 'OTROS CARGOS'
            continue
        elif 'OTROS CREDITOS' in line:
            current_section_type = 'OTROS CREDITOS'
            continue
        elif line in ['MOVIMIENTOS EN QUETZALES', 'MOVIMIENTOS EN DOLARES'] and current_section_type is None:
            current_section_type = 'MOVIMIENTOS'
            
        # Detectar secciones de moneda
        if 'MOVIMIENTOS EN QUETZALES' in line:
            current_currency = 'GTQ'
            in_movements_section = True
            continue
        elif 'MOVIMIENTOS EN DOLARES' in line:
            current_currency = 'USD'
            in_movements_section = True
            continue
        elif 'TOTAL QUETZALES' in line or 'TOTAL DOLARES' in line:
            in_movements_section = False
            continue
            
        # Procesar líneas de transacciones
        if in_movements_section and current_currency:
            # Patrón para transacciones: Fecha operación | Fecha consumo | Descripción | Débito | Crédito
            # Ejemplo: "29/05/23 27/05/23 METAMORFOSIS GT 220.00"
            # Ejemplo: "14/09/21 14/09/21 GRACIAS POR SU PAGO 79.73"
            
            # Patrón para transacciones: Fecha operación | Fecha consumo | Descripción | Monto
            transaction_pattern = re.compile(
                r'^(?P<fecha_op>\d{1,2}/\d{1,2}/\d{2,4})\s+'
                r'(?P<fecha_cons>\d{1,2}/\d{1,2}/\d{2,4})\s+'
                r'(?P<desc>.+?)\s+'
                r'(?P<monto>\d{1,3}(?:,\d{3})*\.\d{2})$'
            )
            
            match = transaction_pattern.match(line)
            if not match:
                continue
            
            # Usar fecha de consumo en lugar de fecha de operación
            fecha_str = match.group('fecha_cons')
            try:
                # Convertir fecha DD/MM/YY o DD/MM/YYYY
                parts = fecha_str.split('/')
                dia, mes, año = parts
                if len(año) == 2:
                    año = int(año)
                    # Convertir año de 2 dígitos a 4 dígitos
                    if año <= 50:
                        año += 2000
                    else:
                        año += 1900
                else:
                    año = int(año)
                
                fecha_consumo = datetime(año, int(mes), int(dia)).date()
            except (ValueError, IndexError):
                fecha_consumo = fecha_corte if fecha_corte else datetime.now().date()
            
            desc = match.group('desc').strip()
            amt = float(match.group('monto').replace(',', ''))
            
            # Determinar tipo de transacción basado en la descripción y sección
            if (current_section_type == 'OTROS CREDITOS' or 
                'PAGO' in desc or 'GRACIAS POR SU PAGO' in desc or 'CREDITO' in desc or 'EXTORNO' in desc):
                tipo = 'credito'
                monto = amt  # Positivo para créditos/pagos/extornos
            else:
                tipo = 'debito'
                monto = -amt  # Negativo para débitos/compras/cargos
                
            # Crear movimiento
            mov = Movimiento(
                fecha=fecha_consumo,
                descripcion=desc,
                lugar=None,
                numero_documento=None,  # Los PDFs de TC no tienen número de documento
                monto=monto,
                moneda=current_currency,
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

    # --- 5) Clasificar movimientos nuevos ---
    clasificar_movimientos()

    return count