import pandas as pd
from datetime import datetime
from ... import db
from ...models import Archivo, Movimiento, Cuenta
from ..classifier import clasificar_movimientos

def load_movements_bac_tc_csv(filepath, archivo_obj):
    """
    Parser para estado de cuenta de Tarjeta de Crédito BAC (.csv).
    El formato esperado tiene:
    - Los movimientos comienzan en la línea 6 (índice 5)
    - Columnas: Fecha, Descripción, Monto Local, Monto Dólares
    - Termina cuando ya no hay fecha válida
    - No tiene ID de movimiento
    
    Retorna el número de movimientos agregados.
    """
    
    # 1) Leer el archivo CSV
    try:
        df = pd.read_csv(filepath, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(filepath, encoding='latin-1')
    
    # Helper para limpiar strings
    def safe_str(val):
        return str(val).strip() if pd.notna(val) else ''
    
    # 2) Extraer metadata de las primeras líneas
    # Basándome en el ejemplo: línea 1 (índice 0) tiene el número de tarjeta y titular
    if len(df) > 0:
        # La primera línea contiene: número de tarjeta, titular, fechas, etc.
        primera_linea = df.iloc[0].values if len(df) > 0 else []
        
        # Extraer número de tarjeta (primer campo de primera línea)
        numero_cuenta = safe_str(primera_linea[0]) if len(primera_linea) > 0 else ''
        # Extraer titular (segundo campo de primera línea)
        titular = safe_str(primera_linea[1]) if len(primera_linea) > 1 else ''
        
        # Si no hay titular en los datos, usar el del archivo_obj
        if not titular:
            titular = archivo_obj.titular or 'Sin titular'
    else:
        numero_cuenta = archivo_obj.numero_cuenta or 'Sin número'
        titular = archivo_obj.titular or 'Sin titular'
    
    # 3) Actualizar archivo_obj
    archivo_obj.tipo_cuenta = 'TC'
    archivo_obj.numero_cuenta = numero_cuenta
    archivo_obj.titular = titular
    archivo_obj.moneda = 'GTQ'  # Por defecto GTQ, se puede ajustar si hay dólares
    db.session.commit()
    
    # 4) Crear o recuperar Cuenta
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
    
    # 5) Procesar movimientos desde la línea 5 (índice 4)
    movimientos_df = df.iloc[4:].copy().reset_index(drop=True)
    
    # 6) Limpiar y preparar datos
    movimientos_validos = []
    
    for idx, row in movimientos_df.iterrows():
        fecha_str = safe_str(row.iloc[0]) if len(row) > 0 else ''
        descripcion = safe_str(row.iloc[1]) if len(row) > 1 else ''
        monto_local_str = safe_str(row.iloc[2]) if len(row) > 2 else '0'
        monto_dolares_str = safe_str(row.iloc[3]) if len(row) > 3 else '0'
        
        # Terminar si no hay fecha válida
        if not fecha_str or fecha_str.lower() in ['', 'nan', 'current', 'balance']:
            break
            
        # Parsear fecha
        try:
            # Intentar formato DD/MM/YYYY
            fecha = datetime.strptime(fecha_str, '%d/%m/%Y').date()
        except ValueError:
            try:
                # Intentar formato MM/DD/YYYY
                fecha = datetime.strptime(fecha_str, '%m/%d/%Y').date()
            except ValueError:
                # Si no se puede parsear, saltar este movimiento
                continue
        
        # Parsear montos
        def parse_monto(val):
            if not val or val.lower() in ['', 'nan']:
                return 0.0
            try:
                # Remover comas y convertir a float
                val = str(val).replace(',', '').strip()
                return float(val)
            except ValueError:
                return 0.0
        
        monto_local = parse_monto(monto_local_str)
        monto_dolares = parse_monto(monto_dolares_str)
        
        # Usar el monto que no sea cero, preferir GTQ
        if monto_local != 0:
            monto = monto_local
            moneda = 'GTQ'
        elif monto_dolares != 0:
            monto = monto_dolares
            moneda = 'USD'
        else:
            continue  # Saltar movimientos sin monto
        
        # Determinar tipo (débito para gastos/compras, crédito para pagos/abonos)
        tipo = 'debito' if monto > 0 else 'credito'
        # Para tarjetas de crédito, los gastos son típicamente positivos pero representan débitos
        # Los pagos/abonos son negativos y representan créditos
        if monto > 0:
            monto = -monto  # Convertir a negativo para gastos
            tipo = 'debito'
        
        movimientos_validos.append({
            'fecha': fecha,
            'descripcion': descripcion,
            'monto': monto,
            'moneda': moneda,
            'tipo': tipo
        })
    
    # 7) Persistir movimientos
    count = 0
    for mov in movimientos_validos:
        movimiento = Movimiento(
            fecha=mov['fecha'],
            descripcion=mov['descripcion'],
            numero_documento='',  # BAC CSV no tiene número de documento
            monto=mov['monto'],
            moneda=mov['moneda'],
            tipo=mov['tipo'],
            cuenta_id=cuenta.id,
            archivo_id=archivo_obj.id
        )
        # Propagar propietario del archivo al movimiento
        if getattr(archivo_obj, 'user_id', None) is not None:
            movimiento.user_id = archivo_obj.user_id
        db.session.add(movimiento)
        count += 1
    
    db.session.commit()
    return count