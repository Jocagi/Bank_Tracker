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
    categoria_tarjeta = 'TC'  # Default
    fecha_corte = None
    
    # Buscar información de cuenta en las primeras líneas
    for i, line in enumerate(lines[:30]):
        # Buscar titular (primera línea con nombre completo)
        if i < 10 and re.match(r'^[A-Z\s]+$', line.strip()) and len(line.strip()) > 10:
            if 'GUATEMALA' not in line and 'ZONA' not in line and 'CALLE' not in line:
                titular = line.strip()
        
        # Buscar número de tarjeta: "XXXX XXXX XXXX 9980 PLATINUM"
        if re.search(r'XXXX XXXX XXXX (\d{4})\s*([A-Z]+)', line):
            match = re.search(r'XXXX XXXX XXXX (\d{4})\s*([A-Z]+)', line)
            if match:
                ultimos_digitos = match.group(1)
                categoria = match.group(2)
                numero_cuenta = f"XXXX-XXXX-XXXX-{ultimos_digitos}"
                categoria_tarjeta = f"TC-{categoria}"  # TC-CLASICA, TC-PLATINUM, etc.
        
        # Buscar fecha de corte: "Fecha de corte: 10 06 2023"
        if 'Fecha de corte:' in line:
            match = re.search(r'Fecha de corte:\s*(\d{1,2})\s+(\d{1,2})\s+(\d{4})', line)
            if match:
                dia, mes, año = match.groups()
                try:
                    fecha_corte = datetime(int(año), int(mes), int(dia)).date()
                except ValueError:
                    fecha_corte = None

    archivo_obj.banco = 'BI'
    archivo_obj.tipo_cuenta = categoria_tarjeta
    archivo_obj.numero_cuenta = numero_cuenta
    archivo_obj.titular = titular
    archivo_obj.moneda = 'GTQ|USD'  # Reporta ambas monedas separadas por |
    db.session.commit()

    # --- 3) Crear o recuperar cuenta ---
    # Buscar cuenta con el número tal como viene del PDF
    cuenta = Cuenta.query.filter_by(
        banco=archivo_obj.banco,
        tipo_cuenta=archivo_obj.tipo_cuenta,
        numero_cuenta=archivo_obj.numero_cuenta
    ).first()
    
    # Si no se encuentra, buscar también sin guiones por si existe en otro formato
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