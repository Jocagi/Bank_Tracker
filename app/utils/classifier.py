import re
from datetime import datetime
from functools import lru_cache
from types import SimpleNamespace
from sqlalchemy.orm import joinedload
from .. import db
from ..models import Regla, Movimiento, Pais, Comercio, CodigoPais, Cuenta


# Campos de tipo texto: se comparan como cadenas (contiene, igual, comodín, regex, etc.).
CAMPOS_TEXTO = {
    'descripcion', 'detalle', 'lugar', 'numero_documento', 'moneda',
    'banco', 'tipo_cuenta', 'cuenta',
}
# Campo numérico: admite comparaciones de magnitud y rangos.
CAMPOS_NUMERICOS = {'monto'}
# Campo de fecha: admite comparaciones cronológicas y de calendario.
CAMPOS_FECHA = {'fecha'}
# Campo de selección cerrada (débito/crédito).
CAMPOS_CHOICE = {'tipo_movimiento'}

DIAS_SEMANA = {
    'lunes': 0, 'martes': 1, 'miercoles': 2, 'miércoles': 2,
    'jueves': 3, 'viernes': 4, 'sabado': 5, 'sábado': 5, 'domingo': 6,
}

CAMPOS_VALIDOS = CAMPOS_TEXTO | CAMPOS_NUMERICOS | CAMPOS_FECHA | CAMPOS_CHOICE

OPERADORES_TEXTO = ('contiene', 'no_contiene', 'igual', 'distinto', 'empieza_con', 'termina_con', 'comodin', 'regex')
OPERADORES_NUMERO = ('igual', 'distinto', 'mayor_que', 'mayor_o_igual', 'menor_que', 'menor_o_igual', 'entre')
OPERADORES_FECHA = ('igual', 'antes_de', 'despues_de', 'entre', 'dia_semana', 'dia_mes', 'mes')
OPERADORES_CHOICE = ('igual', 'distinto')


def operadores_validos_para_campo(campo):
    """Lista de operadores aceptados según el tipo de dato del campo."""
    if campo in CAMPOS_FECHA:
        return OPERADORES_FECHA
    if campo in CAMPOS_NUMERICOS:
        return OPERADORES_NUMERO
    if campo in CAMPOS_CHOICE:
        return OPERADORES_CHOICE
    if campo in CAMPOS_TEXTO:
        return OPERADORES_TEXTO
    return ()


CAMPO_LABELS = {
    'descripcion': 'descripción', 'detalle': 'detalle', 'lugar': 'lugar',
    'numero_documento': 'número de documento', 'moneda': 'moneda', 'monto': 'monto',
    'fecha': 'fecha', 'tipo_movimiento': 'tipo de movimiento', 'banco': 'banco',
    'tipo_cuenta': 'tipo de cuenta', 'cuenta': 'cuenta',
}

OPERADOR_LABELS = {
    'contiene': 'contiene', 'no_contiene': 'no contiene', 'igual': 'es exactamente',
    'distinto': 'es distinto de', 'empieza_con': 'empieza con', 'termina_con': 'termina con',
    'comodin': 'coincide con el patrón', 'regex': 'coincide con la expresión regular',
    'mayor_que': 'es mayor que', 'mayor_o_igual': 'es mayor o igual que',
    'menor_que': 'es menor que', 'menor_o_igual': 'es menor o igual que',
    'entre': 'está entre', 'antes_de': 'es antes del', 'despues_de': 'es después del',
    'dia_semana': 'cae en el día de la semana', 'dia_mes': 'cae en el día del mes', 'mes': 'cae en el mes',
}


def describir_condicion(cond):
    """Texto legible de una condición, p.ej. 'NO banco es exactamente "BI"'."""
    campo_label = CAMPO_LABELS.get(cond.campo, cond.campo)
    operador_label = OPERADOR_LABELS.get(cond.operador, cond.operador)
    prefijo = 'NO ' if cond.negar else ''
    if cond.operador == 'entre':
        detalle = f'"{cond.valor}" y "{cond.valor2}"'
    elif cond.valor:
        detalle = f'"{cond.valor}"'
    else:
        detalle = ''
    return f"{prefijo}{campo_label} {operador_label} {detalle}".strip()


def describir_regla(regla):
    """Texto legible de una regla completa combinando sus condiciones con Y/O."""
    partes = []
    for indice, cond in enumerate(sorted(regla.condiciones, key=lambda c: c.orden)):
        texto = describir_condicion(cond)
        if indice == 0:
            partes.append(texto)
        else:
            conector = 'Y' if (cond.conector or 'AND').upper() == 'AND' else 'O'
            partes.append(f"{conector} {texto}")
    return ' '.join(partes)


def _pais_por_descripcion(descripcion, codigos):
    """Resolve a final code only when it is preceded by a space."""
    match = re.search(r"\s([A-Za-z]{2,3})$", descripcion or '')
    if not match:
        return None

    codigo = match.group(1).upper()
    codigo_pais = next(
        (item for item in codigos if item.activo and item.codigo == codigo),
        None,
    )
    return codigo_pais.pais if codigo_pais else None


def _pais_por_moneda(moneda, paises):
    codigo_por_moneda = {
        'GTQ': 'GT',
        'USD': 'US',
    }
    codigo_iso = codigo_por_moneda.get((moneda or '').strip().upper())
    if not codigo_iso:
        return None
    return next((pais for pais in paises if pais.codigo_iso == codigo_iso), None)


def _actualizar_pais(mov, paises, codigos=None):
    """Assign a country only after the movement is classified as an expense."""
    # Se resuelve por comercio_id (identity map) y no por la relación
    # mov.comercio, que puede quedar desactualizada al reasignar en memoria.
    comercio = db.session.get(Comercio, mov.comercio_id) if mov.comercio_id is not None else None
    if codigos is None:
        codigos = CodigoPais.query.all()
    if comercio and (comercio.tipo_contabilizacion or '').lower() == 'gastos':
        pais = _pais_por_descripcion(mov.descripcion, codigos)
        if pais is None:
            pais = _pais_por_moneda(mov.moneda, paises)
        mov.pais_id = pais.id if pais else None
    else:
        mov.pais_id = None


def _to_float(value):
    try:
        if value is None or value == '':
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        if value is None or value == '':
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_date(value):
    if not value:
        return None
    raw = value.strip() if isinstance(value, str) else value
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _valor_campo(mov, cuenta, campo):
    """Obtiene el valor crudo del movimiento/cuenta para el campo indicado."""
    if campo == 'descripcion':
        return mov.descripcion or ''
    if campo == 'detalle':
        return mov.detalle or ''
    if campo == 'lugar':
        return mov.lugar or ''
    if campo == 'numero_documento':
        return mov.numero_documento or ''
    if campo == 'moneda':
        return mov.moneda or ''
    if campo == 'tipo_movimiento':
        return (mov.tipo or '').lower()
    if campo == 'monto':
        return mov.monto
    if campo == 'fecha':
        return mov.fecha
    if campo == 'banco':
        return cuenta.banco if cuenta else ''
    if campo == 'tipo_cuenta':
        return cuenta.tipo_cuenta if cuenta else ''
    if campo == 'cuenta':
        if not cuenta:
            return ''
        return ' '.join(filter(None, [cuenta.alias, cuenta.numero_cuenta]))
    return ''


@lru_cache(maxsize=4096)
def _patron_compilado(operador, valor):
    """
    Compila (una sola vez) el patrón de una condición 'comodin' o 'regex'.
    La caché interna de ``re`` solo guarda 512 patrones; con más reglas que
    eso, cada evaluación recompilaba el patrón y dominaba el tiempo total
    de clasificación. Retorna None si el patrón es inválido.
    """
    if operador == 'comodin':
        # Comodín '*' equivalente a '.*' dentro de un patrón escapado.
        pattern_str = re.escape(valor or '').replace(r'\*', '.*')
    else:
        pattern_str = valor or ''
    try:
        return re.compile(pattern_str, re.IGNORECASE)
    except re.error:
        return None


def _evaluar_texto(operador, texto, valor, valor2=None):
    if operador in ('comodin', 'regex'):
        patron = _patron_compilado(operador, valor or '')
        return patron is not None and patron.search(texto or '') is not None
    texto_l = (texto or '').strip().lower()
    valor_l = (valor or '').strip().lower()
    if operador == 'contiene':
        return bool(valor_l) and valor_l in texto_l
    if operador == 'no_contiene':
        return not (bool(valor_l) and valor_l in texto_l)
    if operador == 'igual':
        return texto_l == valor_l
    if operador == 'distinto':
        return texto_l != valor_l
    if operador == 'empieza_con':
        return texto_l.startswith(valor_l)
    if operador == 'termina_con':
        return texto_l.endswith(valor_l)
    return False


def _evaluar_numero(operador, numero, valor, valor2=None):
    if numero is None:
        return False
    if operador == 'entre':
        v1, v2 = _to_float(valor), _to_float(valor2)
        if v1 is None or v2 is None:
            return False
        lo, hi = min(v1, v2), max(v1, v2)
        return lo <= numero <= hi
    v = _to_float(valor)
    if v is None:
        return False
    if operador == 'igual':
        return abs(numero - v) < 1e-6
    if operador == 'distinto':
        return abs(numero - v) >= 1e-6
    if operador == 'mayor_que':
        return numero > v
    if operador == 'mayor_o_igual':
        return numero >= v
    if operador == 'menor_que':
        return numero < v
    if operador == 'menor_o_igual':
        return numero <= v
    return False


def _evaluar_fecha(operador, fecha, valor, valor2=None):
    if fecha is None:
        return False
    if operador == 'entre':
        d1, d2 = _to_date(valor), _to_date(valor2)
        if not d1 or not d2:
            return False
        lo, hi = min(d1, d2), max(d1, d2)
        return lo <= fecha <= hi
    if operador == 'igual':
        d = _to_date(valor)
        return d is not None and fecha == d
    if operador == 'antes_de':
        d = _to_date(valor)
        return d is not None and fecha < d
    if operador == 'despues_de':
        d = _to_date(valor)
        return d is not None and fecha > d
    if operador == 'dia_semana':
        raw = (valor or '').strip().lower()
        objetivo = DIAS_SEMANA.get(raw)
        if objetivo is None:
            objetivo = _to_int(raw)
        return objetivo is not None and fecha.weekday() == objetivo
    if operador == 'dia_mes':
        dia = _to_int(valor)
        return dia is not None and fecha.day == dia
    if operador == 'mes':
        mes = _to_int(valor)
        return mes is not None and fecha.month == mes
    return False


def _evaluar_choice(operador, actual, valor):
    actual_l = (actual or '').strip().lower()
    valor_l = (valor or '').strip().lower()
    if operador == 'distinto':
        return actual_l != valor_l
    return actual_l == valor_l


def _evaluar_condicion(condicion, mov, cuenta):
    campo = condicion.campo
    crudo = _valor_campo(mov, cuenta, campo)

    if campo in CAMPOS_FECHA:
        resultado = _evaluar_fecha(condicion.operador, crudo, condicion.valor, condicion.valor2)
    elif campo in CAMPOS_NUMERICOS:
        resultado = _evaluar_numero(condicion.operador, crudo, condicion.valor, condicion.valor2)
    elif campo in CAMPOS_CHOICE:
        resultado = _evaluar_choice(condicion.operador, crudo, condicion.valor)
    else:
        resultado = _evaluar_texto(condicion.operador, crudo, condicion.valor, condicion.valor2)

    return (not resultado) if condicion.negar else resultado


def evaluar_regla(regla, mov, cuenta):
    """
    Evalúa una regla (conjunto ordenado de condiciones) contra un movimiento.
    Las condiciones se combinan secuencialmente de izquierda a derecha según
    su conector (AND/OR), aplicando NOT por condición cuando corresponda.
    """
    condiciones = regla.condiciones
    if not condiciones:
        return False

    resultado = None
    for condicion in condiciones:
        match = _evaluar_condicion(condicion, mov, cuenta)
        if resultado is None:
            resultado = match
        elif (condicion.conector or 'AND').upper() == 'OR':
            resultado = resultado or match
        else:
            resultado = resultado and match
    return bool(resultado)


def cargar_reglas():
    """
    Recupera todas las reglas (con sus condiciones) desde la base de datos.
    Retorna dos listas:
      - reglas_excluir: reglas con tipo 'excluir'
      - reglas_incluir: reglas con tipo 'incluir'
    Las reglas sin condiciones se ignoran (no pueden producir coincidencias).
    """
    reglas = Regla.query.options(joinedload(Regla.condiciones)).order_by(Regla.id).all()
    reglas_excluir = [r for r in reglas if (r.tipo or '').lower() == 'excluir' and r.condiciones]
    reglas_incluir = [r for r in reglas if (r.tipo or '').lower() != 'excluir' and r.condiciones]
    return reglas_excluir, reglas_incluir


def _resolver_cuenta(mov, cache):
    """Obtiene la Cuenta asociada a un movimiento, con cache para evitar N+1."""
    try:
        cuenta = mov.cuenta
    except Exception:
        cuenta = None
    if cuenta is not None:
        return cuenta
    if mov.cuenta_id is None:
        return None
    if mov.cuenta_id not in cache:
        cache[mov.cuenta_id] = db.session.get(Cuenta, mov.cuenta_id)
    return cache[mov.cuenta_id]


def _asignar_comercio(mov, cuenta, reglas_incluir, excl_por_comercio):
    for regla_inc in reglas_incluir:
        if not evaluar_regla(regla_inc, mov, cuenta):
            continue
        reglas_excl = excl_por_comercio.get(regla_inc.comercio_id, [])
        if any(evaluar_regla(r_exc, mov, cuenta) for r_exc in reglas_excl):
            # Está excluido de ESTE comercio → pruebo siguiente inclusión
            continue
        return regla_inc.comercio_id
    return None


def clasificar_movimientos():
    """
    Aplica las reglas de clasificación a los movimientos sin asignar.
    Para cada movimiento:
      - Recorre las reglas de inclusión en orden.
      - Para cada regla de inclusión, verifica primero que NO coincida
        con ninguna regla de exclusión **de ese mismo comercio**.
      - Si coincide inclusión y no hay exclusión para ese comercio,
        asigna mov.comercio_id y continúa con el siguiente movimiento.
    """
    reglas_excluir, reglas_incluir = cargar_reglas()
    paises = Pais.query.all()
    codigos = CodigoPais.query.all()
    cache_cuentas = {}

    # Agrupar exclusiones por comercio_id
    excl_por_comercio = {}
    for regla in reglas_excluir:
        excl_por_comercio.setdefault(regla.comercio_id, []).append(regla)

    # Excluir movimientos que el usuario marcó para no clasificar
    movimientos = Movimiento.query.options(joinedload(Movimiento.cuenta)).filter(
        Movimiento.excluir_clasificacion.is_(False)
    ).all()
    for mov in movimientos:
        if mov.comercio_id is not None:
            _actualizar_pais(mov, paises, codigos)
            continue
        cuenta = _resolver_cuenta(mov, cache_cuentas)
        mov.comercio_id = _asignar_comercio(mov, cuenta, reglas_incluir, excl_por_comercio)
        _actualizar_pais(mov, paises, codigos)

    db.session.commit()


def reclasificar_movimientos():
    """
    Igual que clasificar_movimientos, pero se aplica a **todos** los movimientos,
    reasignando comercios según las reglas. Es la operación costosa: se usa
    solo bajo demanda (botón "Reclasificar todo"). Retorna cuántos
    movimientos cambiaron de comercio.
    """
    reglas_excluir, reglas_incluir = cargar_reglas()
    paises = Pais.query.all()
    codigos = CodigoPais.query.all()
    cache_cuentas = {}

    excl_por_comercio = {}
    for regla in reglas_excluir:
        excl_por_comercio.setdefault(regla.comercio_id, []).append(regla)

    # Durante una reclasificación respetamos movimientos marcados para excluir
    todos = Movimiento.query.options(joinedload(Movimiento.cuenta)).filter(
        Movimiento.excluir_clasificacion.is_(False)
    ).all()
    cambios = 0
    for mov in todos:
        cuenta = _resolver_cuenta(mov, cache_cuentas)
        nuevo = _asignar_comercio(mov, cuenta, reglas_incluir, excl_por_comercio)
        if nuevo != mov.comercio_id:
            mov.comercio_id = nuevo
            cambios += 1
        _actualizar_pais(mov, paises, codigos)

    db.session.commit()
    return cambios


def snapshot_reglas_comercio(comercio_id):
    """
    Copia en memoria (desligada de la sesión) de las reglas actuales de un
    comercio. Debe tomarse ANTES de modificarlas o eliminarlas, para que
    ``reclasificar_comercio`` pueda detectar también los movimientos que
    coincidían con las reglas anteriores.
    """
    reglas = (
        Regla.query.options(joinedload(Regla.condiciones))
        .filter(Regla.comercio_id == comercio_id)
        .all()
    )
    return [
        SimpleNamespace(
            comercio_id=r.comercio_id,
            tipo=r.tipo,
            condiciones=[
                SimpleNamespace(
                    orden=c.orden, conector=c.conector, negar=c.negar, campo=c.campo,
                    operador=c.operador, valor=c.valor, valor2=c.valor2,
                )
                for c in sorted(r.condiciones, key=lambda c: c.orden)
            ],
        )
        for r in reglas
    ]


def reclasificar_comercio(comercio_id, reglas_previas=()):
    """
    Reclasificación incremental tras cambiar las reglas de UN comercio.

    Las reglas de un comercio X solo influyen en un movimiento cuando alguna
    de ellas (incluir o excluir) evalúa verdadero para él: las inclusiones de
    X solo se consideran si coinciden, y sus exclusiones solo se consultan
    cuando ya coincidió una inclusión de X. Por eso los únicos movimientos
    cuya clasificación puede cambiar son:
      - los que hoy están asignados a X, y
      - los que coinciden con alguna regla de X, anterior (``reglas_previas``)
        o actual.
    Solo esos se reevalúan, con el conjunto completo de reglas para respetar
    la prioridad global entre comercios. Retorna cuántos cambiaron.
    """
    reglas_excluir, reglas_incluir = cargar_reglas()
    paises = Pais.query.all()
    codigos = CodigoPais.query.all()
    cache_cuentas = {}

    excl_por_comercio = {}
    for regla in reglas_excluir:
        excl_por_comercio.setdefault(regla.comercio_id, []).append(regla)

    reglas_relevantes = [r for r in reglas_excluir + reglas_incluir if r.comercio_id == comercio_id]
    reglas_relevantes += [r for r in reglas_previas if r.condiciones]

    movimientos = Movimiento.query.options(joinedload(Movimiento.cuenta)).filter(
        Movimiento.excluir_clasificacion.is_(False)
    ).all()
    cambios = 0
    for mov in movimientos:
        cuenta = _resolver_cuenta(mov, cache_cuentas)
        afectado = mov.comercio_id == comercio_id or any(
            evaluar_regla(r, mov, cuenta) for r in reglas_relevantes
        )
        if not afectado:
            continue
        nuevo = _asignar_comercio(mov, cuenta, reglas_incluir, excl_por_comercio)
        if nuevo != mov.comercio_id:
            mov.comercio_id = nuevo
            cambios += 1
        _actualizar_pais(mov, paises, codigos)

    db.session.commit()
    return cambios


def clasificar_movimiento(mov):
    """Clasifica un único movimiento con el conjunto completo de reglas."""
    if mov.excluir_clasificacion:
        return mov.comercio_id
    reglas_excluir, reglas_incluir = cargar_reglas()
    excl_por_comercio = {}
    for regla in reglas_excluir:
        excl_por_comercio.setdefault(regla.comercio_id, []).append(regla)
    cuenta = _resolver_cuenta(mov, {})
    mov.comercio_id = _asignar_comercio(mov, cuenta, reglas_incluir, excl_por_comercio)
    _actualizar_pais(mov, Pais.query.all(), CodigoPais.query.all())
    db.session.commit()
    return mov.comercio_id


def previsualizar_clasificacion(movimientos):
    """
    Dada una lista de objetos Movimiento (no persistidos),
    devuelve una lista de tuplas (movimiento, comercio_id_asignado o None).
    """
    reglas_excluir, reglas_incluir = cargar_reglas()
    cache_cuentas = {}
    excl_por_comercio = {}
    for regla in reglas_excluir:
        excl_por_comercio.setdefault(regla.comercio_id, []).append(regla)

    resultados = []
    for mov in movimientos:
        # Si el movimiento (objeto en memoria) tiene atributo excluir_clasificacion True, saltarlo
        if getattr(mov, 'excluir_clasificacion', False):
            resultados.append((mov, None))
            continue
        cuenta = _resolver_cuenta(mov, cache_cuentas)
        comercio_asignado = _asignar_comercio(mov, cuenta, reglas_incluir, excl_por_comercio)
        resultados.append((mov, comercio_asignado))

    return resultados
