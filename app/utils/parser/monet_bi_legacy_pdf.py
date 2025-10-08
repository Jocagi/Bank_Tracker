"""
Parser para PDFs de cuentas monetarias del Banco Industrial 
enviados por correo electrónico ANTES de febrero 2023 (formato legacy).
"""

import pdfplumber
import re
from datetime import datetime
from app.models import Movimiento, Cuenta, db
from app.utils.classifier import clasificar_movimientos


def parse_monet_bi_legacy_pdf_file(filepath, archivo_obj):
    """
    Parsea un PDF de cuenta monetaria BI formato legacy (anterior a feb 2023).
    
    Formato esperado:
    - Header: "MONEDA QUETZALES DEL MES DE ENERO 2022"
    - Número de cuenta: "185-007460-8"  
    - Titular: "GIRON MARQUEZ JOSE CARLOS"
    - Transacciones: Dia | Docto. | Descripción | Débito | Crédito | Saldo
    """
    
    # --- 1) Extraer texto del PDF ---
    with pdfplumber.open(filepath) as pdf:
        text_content = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_content += page_text + "\n"

    if not text_content.strip():
        raise ValueError("No se pudo extraer texto del PDF")

    lines = text_content.split('\n')

    # --- 2) Extraer metadatos del header ---
    
    # Buscar el mes y año del estado de cuenta
    fecha_corte = None
    mes_año_pattern = re.compile(r'DEL\s*MES\s*DE\s+(\w+)\s*(\d{4})', re.IGNORECASE)
    
    for line in lines[:5]:  # Buscar en las primeras líneas
        match = mes_año_pattern.search(line)
        if match:
            mes_texto, año = match.groups()
            # Convertir nombre de mes a número
            meses = {
                'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6,
                'JULIO': 7, 'AGOSTO': 8, 'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12
            }
            mes_num = meses.get(mes_texto.upper())
            if mes_num:
                # Usar el último día del mes como fecha de corte
                if mes_num == 2:
                    ultimo_dia = 28  # Simplificado para febrero
                elif mes_num in [4, 6, 9, 11]:
                    ultimo_dia = 30
                else:
                    ultimo_dia = 31
                fecha_corte = datetime(int(año), mes_num, ultimo_dia).date()
            break

    # Buscar número de cuenta
    numero_cuenta = None
    cuenta_pattern = re.compile(r'NUMERO\s*DE\s*CUENTA\s+(\d{3}-\d{6}-\d)', re.IGNORECASE)
    
    for line in lines[:10]:
        match = cuenta_pattern.search(line)
        if match:
            numero_cuenta = match.group(1)
            break

    # Buscar titular - generalmente está después del número de cuenta
    titular = None
    for i, line in enumerate(lines[:10]):
        if numero_cuenta and numero_cuenta in line:
            # El titular suele estar en la siguiente línea
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Limpiar la línea del titular de caracteres extraños
                if next_line and not re.match(r'^TARJETAS|^\d|^LASCUENTAS', next_line):
                    titular = next_line
                    break

    if not numero_cuenta:
        raise ValueError("No se pudo extraer el número de cuenta del PDF")

    # --- 3) Buscar o crear cuenta ---
    archivo_obj.banco = 'BI'
    archivo_obj.tipo_cuenta = 'MONETARIA'
    archivo_obj.numero_cuenta = numero_cuenta
    archivo_obj.titular = titular or 'TITULAR NO IDENTIFICADO'
    archivo_obj.moneda = 'GTQ'

    # Buscar cuenta existente (con y sin guiones)
    cuenta = None
    numero_sin_guiones = numero_cuenta.replace('-', '')
    
    cuentas_similares = Cuenta.query.filter(
        (Cuenta.numero_cuenta == numero_cuenta) |
        (Cuenta.numero_cuenta == numero_sin_guiones)
    ).all()
    
    if cuentas_similares:
        # Buscar coincidencia exacta primero
        for cuenta_existente in cuentas_similares:
            if cuenta_existente.numero_cuenta == numero_cuenta:
                cuenta = cuenta_existente
                break
        
        # Si no hay coincidencia exacta, buscar sin guiones
        if not cuenta:
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
    in_transactions_section = False
    saldo_anterior_movimiento = None
    
    for line in lines:
        line = line.strip()
        
        # Detectar inicio de sección de transacciones
        if 'Dia Docto. Descripción Débito Crédito Saldo' in line:
            in_transactions_section = True
            continue
            
        # Detectar fin de sección de transacciones
        if '****ULTIM' in line or 'MOVIMIENTO MENSUAL DE CHEQUES' in line:
            in_transactions_section = False
            continue
        
        # Saltar líneas que no son transacciones
        if not in_transactions_section:
            continue
            
        # Capturar saldo anterior
        if '****SALDO ANTERIOR****' in line:
            # Extraer el saldo anterior de la línea
            saldo_match = re.search(r'(\d{1,3}(?:,\d{3})*\.\d{2})$', line)
            if saldo_match:
                saldo_anterior_movimiento = float(saldo_match.group(1).replace(',', ''))
            continue
            
        # Patrón para transacciones: Día | Docto | Descripción | Débito/Crédito | Saldo
        # Ejemplo: "01 245268 NOTADEBITOBANCAMOVIL 3,283.89 2,020.40"
        transaction_pattern = re.compile(
            r'^(\d{1,2})\s+'           # Día (1-2 dígitos)
            r'(\d+)\s+'                # Número de documento  
            r'(.+?)\s+'                # Descripción (non-greedy)
            r'(\d{1,3}(?:,\d{3})*\.\d{2})\s+'  # Primer monto (débito o crédito)
            r'(\d{1,3}(?:,\d{3})*\.\d{2})$'    # Saldo final
        )
        
        match = transaction_pattern.match(line)
        if not match:
            continue
            
        dia_str, numero_doc, descripcion, monto_str, saldo_str = match.groups()
        
        # Construir fecha usando el día del movimiento y el mes/año del estado
        try:
            dia = int(dia_str)
            if fecha_corte:
                fecha_movimiento = datetime(fecha_corte.year, fecha_corte.month, dia).date()
            else:
                fecha_movimiento = datetime.now().date()
        except (ValueError, TypeError):
            fecha_movimiento = fecha_corte if fecha_corte else datetime.now().date()
        
        # Limpiar descripción
        desc = descripcion.strip()
        
        # Convertir monto y saldo
        monto_valor = float(monto_str.replace(',', ''))
        saldo_actual = float(saldo_str.replace(',', ''))
        
        # Determinar si es débito o crédito basado en el cambio matemático del saldo
        if saldo_anterior_movimiento is not None:
            # Calcular si el saldo aumentó o disminuyó
            cambio_saldo = saldo_actual - saldo_anterior_movimiento
            
            # Si el cambio del saldo es positivo, fue un crédito
            # Si el cambio del saldo es negativo, fue un débito  
            if cambio_saldo > 0:
                tipo = 'credito'
                monto = monto_valor  # Positivo para créditos
            else:
                tipo = 'debito'
                monto = -monto_valor  # Negativo para débitos
        else:
            # Fallback: usar heurística de palabras clave para la primera transacción
            if any(keyword in desc.upper() for keyword in [
                'CREDITO', 'DEPOSITO', 'PLANILLA', 'PAGO', 'SALARIO', 'SUELDO', 
                'TRANSFERENCIA RECIBIDA', 'INTERES', 'ABONO', 'BONIFICACION'
            ]):
                tipo = 'credito'
                monto = monto_valor  # Positivo para créditos
            else:
                tipo = 'debito'  
                monto = -monto_valor  # Negativo para débitos
        
        # Actualizar saldo_anterior_movimiento para la próxima iteración
        saldo_anterior_movimiento = saldo_actual
        
        # Crear movimiento
        mov = Movimiento(
            fecha=fecha_movimiento,
            descripcion=desc,
            lugar=None,
            numero_documento=numero_doc,
            monto=monto,
            moneda='GTQ',  # Siempre GTQ en este formato
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