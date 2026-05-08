import re
import os
import logging
from datetime import datetime
import pdfplumber
import pandas as pd

from ... import db
from ...models import Movimiento, Cuenta

logging.getLogger('pdfminer').setLevel(logging.WARNING)


_MESES_ES = {
    'ene': 1,
    'feb': 2,
    'mar': 3,
    'abr': 4,
    'may': 5,
    'jun': 6,
    'jul': 7,
    'ago': 8,
    'sep': 9,
    'oct': 10,
    'nov': 11,
    'dic': 12,
}


def _undouble_text(texto):
    if texto is None:
        return ''
    s = str(texto)
    # En estados Nexa algunos PDFs duplican caracteres: "JJoosséé" -> "José"
    # Colapsar repeticiones consecutivas deja texto utilizable para metadatos.
    return re.sub(r'(.)\1+', r'\1', s)


def _parse_amount_text(token):
    if token is None:
        return None
    s = _undouble_text(str(token)).strip()
    s = re.sub(r'[^0-9,\.-]', '', s)
    if not s:
        return None
    if s.count('.') > 1:
        first = s.find('.')
        s = s[:first + 1] + s[first + 1:].replace('.', '')
    s = s.replace(',', '')
    try:
        return float(s)
    except Exception:
        return None


def _extract_first_amount_near_label(lines, label):
    label_l = label.lower()
    for idx, line in enumerate(lines[:80]):
        if label_l in (line or '').lower():
            candidates = [line]
            if idx + 1 < len(lines):
                candidates.append(lines[idx + 1])
            if idx + 2 < len(lines):
                candidates.append(lines[idx + 2])

            for cand in candidates:
                for token in re.findall(r'Q\s*[0-9\.,-]+|[0-9][0-9\.,-]*', cand or ''):
                    value = _parse_amount_text(token)
                    if value is not None:
                        return value
    return None


def _parse_fecha_es(valor):
    if valor is None:
        return None
    if hasattr(valor, 'year') and hasattr(valor, 'month') and hasattr(valor, 'day'):
        try:
            return valor.date() if hasattr(valor, 'date') else valor
        except Exception:
            pass

    texto = str(valor).strip()
    if not texto:
        return None

    m = re.match(r'^(\d{1,2})\s+([A-Za-zÁÉÍÓÚáéíóú]{3,})\s+(\d{4})$', texto)
    if m:
        dia = int(m.group(1))
        mes_txt = m.group(2).lower()[:3]
        anio = int(m.group(3))
        mes = _MESES_ES.get(mes_txt)
        if mes:
            try:
                return datetime(anio, mes, dia).date()
            except Exception:
                return None

    try:
        dt = pd.to_datetime(texto, dayfirst=True, errors='coerce')
        if pd.isna(dt):
            return None
        return dt.date()
    except Exception:
        return None


def load_movements_monet_nexa_pdf(filepath, archivo_obj):
    """
    Parser para estados de cuenta monetarios del Banco Nexa.
    - Extrae número de cuenta, moneda y "Saldo Final" del encabezado.
    - Extrae la tabla de movimientos y guarda cada `Movimiento`.
    - Actualiza/crea la `Cuenta` y establece su `saldo` al "Saldo Final".
    Retorna el número de movimientos agregados.
    """
    # obtener metadata y dataframe parseado por la función dedicada
    info, df = parse_monet_nexa_metadata(filepath)

    # 2) Actualizar metadatos en archivo_obj (usar getattr seguro)
    archivo_obj.tipo_cuenta = info.get('tipo_cuenta') or 'MONET'
    archivo_obj.moneda = info.get('moneda') or 'GTQ'
    archivo_obj.numero_cuenta = info.get('numero_cuenta') or ''
    archivo_obj.titular = info.get('titular') or getattr(archivo_obj, 'titular', 'Desconocido')
    db.session.commit()

    # 3) Buscar o crear la cuenta
    cuenta = Cuenta.find_by_numero(archivo_obj.numero_cuenta)
    if cuenta:
        try:
            if cuenta.banco != archivo_obj.banco:
                cuenta = None
            elif info.get('titular') and (not (cuenta.titular or '').strip() or (cuenta.titular or '').strip().lower() == 'desconocido'):
                cuenta.titular = info.get('titular')
                db.session.add(cuenta)
                db.session.commit()
        except Exception:
            cuenta = None

    if not cuenta:
        cuenta = Cuenta(
            banco=archivo_obj.banco,
            tipo_cuenta=archivo_obj.tipo_cuenta,
            numero_cuenta=archivo_obj.numero_cuenta,
            titular=archivo_obj.titular or 'Desconocido',
            moneda=archivo_obj.moneda or 'GTQ'
        )
        if getattr(archivo_obj, 'user_id', None) is not None:
            cuenta.user_id = archivo_obj.user_id
        db.session.add(cuenta)
        db.session.commit()

    # df ya fue obtenido por parse_monet_nexa_metadata
    if df is None or df.empty:
        raise ValueError("No se detectó la tabla de movimientos en el PDF (Nexa).")

    # Normalizar columnas: intentar detectar columnas comunes
    colmap = {}
    for c in df.columns:
        cn = c.strip().lower()
        if 'fecha' in cn:
            colmap[c] = 'fecha'
        elif 'descripcion' in cn or 'detalle' in cn:
            colmap[c] = 'descripcion'
        elif 'doc' in cn or 'documento' in cn:
            colmap[c] = 'documento'
        elif 'monto' in cn or 'cargo' in cn or 'abono' in cn or 'debito' in cn or 'credito' in cn:
            colmap[c] = 'monto'
        elif 'saldo' in cn:
            colmap[c] = 'saldo'

    df = df.rename(columns=colmap)

    # Coerce and clean
    if 'fecha' in df.columns:
        df['fecha'] = df['fecha'].apply(_parse_fecha_es)

    if 'monto' in df.columns:
        df['monto'] = (
            df['monto']
            .astype(str)
            .str.replace(r"[^0-9\.-]", "", regex=True)
            .replace('', '0')
            .astype(float)
        )
    else:
        # intentar inferir monto sumando columnas cargo/abono
        df['monto'] = 0.0

    moneda = archivo_obj.moneda or 'GTQ'
    df['moneda'] = moneda

    # 5) Insertar movimientos
    # Filtrar filas no válidas: líneas de separadores o sin fecha
    if 'raw' in df.columns:
        df = df[~df['raw'].str.contains('ULTIM|ULTIMA|-----', case=False, na=False)].copy()
    if 'fecha' in df.columns:
        df = df[df['fecha'].notna()].copy()

    if 'saldo' in df.columns:
        df['saldo'] = (
            df['saldo']
            .astype(str)
            .str.replace(r"[^0-9\.-]", "", regex=True)
            .replace('', '0')
            .astype(float)
        )

    # Inferir signo del monto usando la variación de saldo: delta = saldo_actual - saldo_previo
    # Si delta ≈ +monto => crédito; si delta ≈ -monto => débito.
    if 'monto' in df.columns and 'saldo' in df.columns and not df.empty:
        prev_saldo = info.get('saldo_inicial')
        signed = []
        for _, row in df.iterrows():
            amount_abs = abs(float(row.get('monto') or 0.0))
            saldo_actual = row.get('saldo')
            if prev_saldo is None:
                signed_amount = amount_abs
            else:
                delta = round(float(saldo_actual) - float(prev_saldo), 2)
                if abs(delta - amount_abs) <= abs(delta + amount_abs):
                    signed_amount = amount_abs
                else:
                    signed_amount = -amount_abs
            signed.append(signed_amount)
            prev_saldo = saldo_actual
        df['monto'] = signed

    for _, row in df.iterrows():
        mov = Movimiento(
            fecha=row.get('fecha'),
            descripcion=(row.get('descripcion') or '').strip(),
            numero_documento=row.get('documento') or '',
            monto=row.get('monto') or 0.0,
            moneda=moneda,
            tipo='debito' if (row.get('monto') or 0) < 0 else 'credito',
            cuenta_id=cuenta.id,
            archivo_id=archivo_obj.id
        )
        if getattr(archivo_obj, 'user_id', None) is not None:
            mov.user_id = archivo_obj.user_id
        db.session.add(mov)

    # 6) Actualizar saldo final en la cuenta si fue detectado
    if info.get('saldo_final') is not None:
        try:
            cuenta.saldo = info['saldo_final']
            db.session.add(cuenta)
        except Exception:
            pass

    db.session.commit()

    # contar únicamente filas que se insertaron (asumimos df length)
    return len(df)


def parse_monet_nexa_metadata(filepath):
    """
    Extrae metadata (numero_cuenta, moneda, saldo_final, titular) y el DataFrame
    de movimientos del PDF sin tocar la base de datos. Retorna (info, df).
    """
    # 1) Leer todo el texto para capturar encabezado (líneas iniciales)
    with pdfplumber.open(filepath) as pdf:
        all_lines = []
        for page in pdf.pages:
            txt = page.extract_text() or ""
            all_lines.extend(txt.split('\n'))

    clean_lines = [_undouble_text((line or '').strip()) for line in all_lines if (line or '').strip()]

    info = {
        'titular': None,
        'numero_cuenta': None,
        'moneda': None,
        'saldo_inicial': None,
        'saldo_final': None,
        'tipo_cuenta': 'MONET'
    }

    # Buscar patrones comunes en las primeras 40 líneas
    for line in all_lines[:40]:
        l = line.strip()
        # Ejemplo esperado: "Cuenta: 10-10036578-9"
        if info['numero_cuenta'] is None and re.search(r'Cuenta\s*[:\-]', l, re.IGNORECASE):
            m = re.search(r'([0-9]{1,2}[- ][0-9A-Za-z\-]+[- ][0-9A-Za-z]+)', l)
            if m:
                info['numero_cuenta'] = m.group(1).replace(' ', '').strip()
            else:
                # fallback: tomar último token
                parts = l.split()
                if parts:
                    info['numero_cuenta'] = parts[-1].strip()

        # Moneda: puede aparecer como "Moneda: Quetzales" o "QTZ" o "GTQ"
        if info['moneda'] is None and re.search(r'Moneda|Divisa', l, re.IGNORECASE):
            if 'quetzal' in l.lower() or 'quetzales' in l.lower() or 'gtq' in l.lower() or 'qtz' in l.lower() or 'q ' in l.lower():
                info['moneda'] = 'GTQ'
            else:
                # tomar abreviatura si está presente
                m = re.search(r'\b(GTQ|QTZ|USD)\b', l, re.IGNORECASE)
                if m:
                    info['moneda'] = m.group(1).upper().replace('QTZ', 'GTQ')

        # Saldo Final: puede aparecer como "Saldo Final" o "Saldo al cierre" seguido de número
        if info['saldo_final'] is None and re.search(r'Saldo\s*Final|Saldo al cierre|Saldo al', l, re.IGNORECASE):
            m = re.search(r'([\d\.,\-]+)', l.replace(',', ''))
            if m:
                try:
                    info['saldo_final'] = float(m.group(1).replace(',', ''))
                except Exception:
                    # intentar limpiar caracteres
                    digits = re.sub(r'[^0-9\.-]', '', l)
                    try:
                        info['saldo_final'] = float(digits)
                    except Exception:
                        info['saldo_final'] = None

    # Titular: normalmente aparece en la línea siguiente al encabezado principal
    # "Estado de Cuenta Monetaria ... <numero_cuenta>"
    if info['titular'] is None and clean_lines:
        for idx, line in enumerate(clean_lines[:20]):
            low = line.lower()
            if 'estado de cuenta' in low and ('monetaria' in low or 'quetzal' in low):
                for j in range(idx + 1, min(idx + 6, len(clean_lines))):
                    cand = clean_lines[j].strip()
                    cand_low = cand.lower()
                    if not cand:
                        continue
                    if any(x in cand_low for x in ('fecha:', 'saldo ', 'operaciones', 'tarjeta', 'nexa', 'contáctanos', 'contactanos', 'gt63', 'no. de ref')):
                        continue
                    if re.search(r'\d{4,}', cand):
                        continue
                    if len(re.findall(r'[A-Za-zÁÉÍÓÚáéíóúÑñ]', cand)) < 5:
                        continue
                    info['titular'] = cand
                    break
                if info['titular']:
                    break

    # Normalizar texto colapsando caracteres repetidos para mejorar extracción
    joined = '\n'.join(all_lines)
    joined_norm = re.sub(r'(.)\1+', r'\1', joined)

    if info['saldo_inicial'] is None:
        info['saldo_inicial'] = _extract_first_amount_near_label(all_lines, 'Saldo Inicial')

    if info['saldo_final'] is None:
        info['saldo_final'] = _extract_first_amount_near_label(all_lines, 'Saldo Final')

    # Asegurar moneda por defecto si se detectó palabra 'Quetzal' en todo el texto
    if info['moneda'] is None:
        if 'quetzal' in joined_norm.lower() or 'quetzales' in joined_norm.lower():
            info['moneda'] = 'GTQ'

    # Intentar extraer numero de cuenta buscando patrones en todo el texto
    if info['numero_cuenta'] is None:
        # patrón típico: 10-10036578-9 o similar — buscar en texto normalizado
        m = re.search(r'\b\d{1,2}[- ]\d{6,12}[- ]\d\b', joined_norm)
        if m:
            candidate = m.group(0).replace(' ', '')
            parts = re.split(r'[- ]', candidate)
            # esperar formato 2-8-1
            if len(parts) == 3 and len(parts[0]) == 2 and len(parts[1]) == 8 and len(parts[2]) == 1:
                info['numero_cuenta'] = candidate
            else:
                # no es del largo esperado, intentar derivar del filename
                m2 = re.search(r'(\d{11})', os.path.basename(filepath or ''))
                if m2:
                    s = m2.group(1)
                    info['numero_cuenta'] = f"{s[:2]}-{s[2:10]}-{s[10]}"
        else:
            # fallback: intentar extraer secuencia de 11 dígitos del nombre de archivo y formatearla
            fn = os.path.basename(filepath or '')
            m2 = re.search(r'(\d{11})', fn)
            if m2:
                s = m2.group(1)
                # construir formato 2-8-1
                info['numero_cuenta'] = f"{s[:2]}-{s[2:10]}-{s[10]}"


    # Extraer tablas de movimientos con pdfplumber
    tables = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            tbl = page.extract_table({
                "vertical_strategy":   "lines",
                "horizontal_strategy": "lines"
            })
            if tbl and len(tbl) > 0:
                # Detectar si la primera fila es un header real (contiene palabras como Fecha/Descripción)
                header_candidate = tbl[0]
                header_text = ' '.join([str(x) for x in header_candidate]).lower()
                if any(h in header_text for h in ('fecha', 'descripción', 'descripcion', 'saldo', 'debito', 'credito', 'no. de ref', 'no de ref')) and len(tbl) > 1:
                    tables.append(pd.DataFrame(tbl[1:], columns=tbl[0]))
                else:
                    # Tratar todas las filas como una sola columna 'raw'
                    rows = [[r[0] if len(r) > 0 else ''] for r in tbl]
                    tables.append(pd.DataFrame(rows, columns=['raw']))

    df = None
    if tables:
        df = pd.concat(tables, ignore_index=True)

    # Si df existe pero tiene una sola columna grande, intentar parsear filas en columnas útiles
    if df is not None and len(df.columns) == 1:
        # renombrar columna a 'raw'
        df = df.rename(columns={df.columns[0]: 'raw'})
        # intentar extraer campos usando regex por fila
        rows = []
        for _, r in df.iterrows():
            raw = (r.get('raw') or '').strip()
            # patrón: Fecha Doc Descripción Qmonto Qsaldo
            m = re.match(r"^(?P<fecha>\d{1,2}\s+\w+\s+\d{4})\s+(?P<doc>\d+)\s+(?P<desc>.+?)\s+Q(?P<monto>[\d,]+\.?\d*)\s+Q(?P<saldo>[\d,]+\.?\d*)$", raw)
            if m:
                rows.append({
                    'fecha': m.group('fecha'),
                    'documento': m.group('doc'),
                    'descripcion': m.group('desc'),
                    'monto': m.group('monto'),
                    'saldo': m.group('saldo'),
                    'raw': raw
                })
            else:
                # fallback: intentar extraer montos con 'Q' y tomar resto como descripción
                parts = re.findall(r'Q[\d,]+\.?\d*', raw)
                monto = None
                saldo = None
                if parts:
                    if len(parts) >= 2:
                        monto = parts[-2].lstrip('Q')
                        saldo = parts[-1].lstrip('Q')
                    elif len(parts) == 1:
                        monto = parts[0].lstrip('Q')
                # quitar montos de la cadena para obtener descripción
                desc = re.sub(r'Q[\d,]+\.?\d*', '', raw).strip()
                # intentar fecha al inicio
                fecha = None
                m2 = re.match(r'^(\d{1,2}\s+\w+\s+\d{4})', raw)
                if m2:
                    fecha = m2.group(1)
                rows.append({
                    'fecha': fecha,
                    'documento': None,
                    'descripcion': desc,
                    'monto': monto,
                    'saldo': saldo,
                    'raw': raw
                })

        if rows:
            df = pd.DataFrame(rows)
            # limpiar campos numéricos
            for col in ('monto', 'saldo'):
                if col in df.columns:
                    df[col] = df[col].astype(str).str.replace(r"[^0-9\.-]", "", regex=True).replace('', '0')
                    df[col] = df[col].astype(float)

    # Si no se detectó saldo_final por texto, intentar tomar el último saldo de la tabla parseada
    if info.get('saldo_final') is None and df is not None and 'saldo' in df.columns and not df['saldo'].isnull().all():
        try:
            last_saldo = df['saldo'].dropna().iloc[-1]
            info['saldo_final'] = float(last_saldo)
        except Exception:
            pass

    # Si todavía no hay moneda, detectar por presencia de 'Q' en el cuerpo
    if info.get('moneda') is None:
        joined = '\n'.join(all_lines)
        if 'Q' in joined or 'quetzal' in joined.lower():
            info['moneda'] = 'GTQ'

    return info, df
