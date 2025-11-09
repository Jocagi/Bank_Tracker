import re
import pdfplumber
from datetime import datetime
from ... import db
from ...models import Archivo, Movimiento, Cuenta
from .cuenta_utils import get_or_create_cuenta
from ..classifier import clasificar_movimientos

def load_movements_bi_monet_email_pdf(filepath, archivo_obj):
    """
    Parser para estado de cuenta monetaria del Banco Industrial (PDF enviado por email):
      1) Extrae encabezado y metadata (titular, cuenta, mes).
      2) Extrae el SALDO ANTERIOR.
      3) Lee cada línea de movimiento:
         - Día, documento, descripción, débito, crédito, saldo.
         - Determina tipo (débito/crédito) según la columna correspondiente.
         - Moneda por defecto GTQ (Quetzales).
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
    titular = 'Desconocido'
    numero_cuenta = 'Desconocido'
    
    # Buscar información de cuenta en las primeras líneas
    for i, line in enumerate(lines[:20]):
        # Buscar número de cuenta: "Número 185-007460-8"
        if 'Número' in line and re.search(r'\d{3}-\d{6}-\d', line):
            match = re.search(r'(\d{3}-\d{6}-\d)', line)
            if match:
                numero_cuenta = match.group(1)
        
        # Buscar titular y fecha (línea que contiene nombre completo seguido de mes/año)
        if re.search(r'[A-Z_\s]+ (ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)/\d{2}', line):
            # Extraer la parte del nombre antes del mes y también extraer mes/año
            match = re.match(r'(.+?)\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)/(\d{2})', line)
            if match:
                titular = match.group(1).strip().replace('_', ' ')  # Reemplazar guiones bajos por espacios
                mes_nombre = match.group(2)
                año_corto = match.group(3)
                # Convertir año de 2 dígitos a 4 dígitos
                current_year = int(año_corto)
                if current_year <= 50:  # Asumiendo que 00-50 es 2000-2050
                    current_year += 2000
                else:  # 51-99 es 1951-1999
                    current_year += 1900
                
                # Guardar mes y año para usar en las transacciones
                meses = {
                    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6,
                    'JULIO': 7, 'AGOSTO': 8, 'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12
                }
                header_info['mes'] = meses[mes_nombre]
                header_info['año'] = current_year

    archivo_obj.banco = 'BI'
    archivo_obj.tipo_cuenta = 'MONET'
    archivo_obj.numero_cuenta = numero_cuenta
    archivo_obj.titular = titular
    archivo_obj.moneda = 'GTQ'
    db.session.commit()

    # --- 3) Crear o recuperar cuenta (consultar números alternativos primero) ---
    # --- 3) Crear o recuperar cuenta (centralizado) ---
    cuenta = get_or_create_cuenta(archivo_obj)

    # --- 4) Buscar SALDO ANTERIOR ---
    prev_balance = None
    for line in lines:
        # Buscar línea que contenga "****SALDO ANTERIOR****" seguido del monto
        if '****SALDO ANTERIOR****' in line:
            # Extraer el saldo que está al final de la línea
            match = re.search(r'(\d{1,3}(?:,\d{3})*\.\d{2})$', line.strip())
            if match:
                prev_balance = float(match.group(1).replace(',', ''))
                break

    # --- 5) Procesar cada línea de transacción ---
    # Patrón para líneas de transacciones: Día Doc. Descripción Débito Crédito Saldo
    # Ejemplo: "01 194641 NOTA DEBITO PAGOS DE IMPUESTOS DECLARAGU 7.50 1,935.09"
    # O con crédito: "02 77250 NOTA CREDITO BANCA MOVIL 400.00 2,233.09"
    
    count = 0
    
    for line in lines:
        line = line.strip()
        
        # Saltar líneas que no son transacciones
        if ('****SALDO ANTERIOR****' in line or 
            'Día Doc. Descripción' in line or 
            '**** ULTIMA LINEA ****' in line or
            'Totales' in line or
            'Pag ' in line or
            len(line) < 10):
            continue
            
        # Patrón más flexible para transacciones: 
        # Intenta detectar si la línea tiene el formato: Día Doc Descripción Monto Saldo
        # donde Monto puede estar en columna de débito o crédito
        transaction_pattern = re.compile(
            r'^(?P<dia>\d{1,2})\s+'
            r'(?P<doc>\d+)\s+'
            r'(?P<desc>.+?)\s+'
            r'(?P<monto>\d{1,3}(?:,\d{3})*\.\d{2})\s+'
            r'(?P<saldo>\d{1,3}(?:,\d{3})*\.\d{2})$'
        )
        
        m = transaction_pattern.match(line)
        
        if not m or prev_balance is None:
            continue

        # Extraer campos básicos
        dia = int(m.group('dia'))
        doc = m.group('doc')
        desc = m.group('desc').strip()
        amt = float(m.group('monto').replace(',', ''))
        bal = float(m.group('saldo').replace(',', ''))
        
        # Determinar si es débito o crédito comparando saldos
        if bal > prev_balance:
            tipo = 'credito'
            monto = amt  # Positivo para créditos
        else:
            tipo = 'debito'
            monto = -amt  # Negativo para débitos

        # Usar el mes y año extraídos del encabezado
        mes_actual = header_info.get('mes', datetime.now().month)
        año_actual = header_info.get('año', datetime.now().year)

        # Construir fecha completa
        try:
            fecha = datetime(año_actual, mes_actual, dia).date()
        except ValueError:
            # En caso de día inválido (ej: 31 de febrero), usar el último día del mes
            import calendar
            last_day = calendar.monthrange(año_actual, mes_actual)[1]
            fecha = datetime(año_actual, mes_actual, min(dia, last_day)).date()

        # Crear movimiento
        mov = Movimiento(
            fecha=fecha,
            descripcion=desc,
            lugar=None,
            numero_documento=doc,
            monto=monto,
            moneda='GTQ',
            tipo=tipo,
            cuenta_id=cuenta.id,
            archivo_id=archivo_obj.id
        )
        
        # Propagar propietario del archivo al movimiento
        if getattr(archivo_obj, 'user_id', None) is not None:
            mov.user_id = archivo_obj.user_id
            
        db.session.add(mov)
        count += 1
        prev_balance = bal

    db.session.commit()

    # --- 6) Clasificar movimientos nuevos ---
    clasificar_movimientos()

    return count