import re
from .. import db
from ..models import Regla, Movimiento

def cargar_reglas():
    """
    Recupera todas las reglas desde la base de datos.
    Retorna dos listas de tuplas (regla, patrón):
      - reglas_excluir: reglas con tipo 'excluir'
      - reglas_incluir: reglas con tipo 'incluir'
    Se admite:
        * Comodines: '*' → '.*' en regex.
        * Coincidencia exacta: criterio que empieza con '='.
    """
    reglas_excluir = []
    reglas_incluir = []

    for regla in Regla.query.all():
        raw = (regla.criterio or '').strip()
        if not raw:
            continue

        # 1) Si comienza con '=' → coincidencia exacta
        if raw.startswith('='):
            exact = raw[1:].strip()
            pattern_str = r'^' + re.escape(exact) + r'$'
        else:
            # 2) Escapar y luego transformar '*' en '.*'
            escaped = re.escape(raw)
            pattern_str = escaped.replace(r'\*', '.*')

        try:
            patron = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            # Si el patrón es inválido, lo descartamos
            continue

        if regla.tipo.lower() == 'excluir':
            reglas_excluir.append((regla, patron))
        else:
            reglas_incluir.append((regla, patron))

    return reglas_excluir, reglas_incluir


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

    # Agrupar exclusiones por comercio_id
    excl_por_comercio = {}
    for regla, patron in reglas_excluir:
        excl_por_comercio.setdefault(regla.comercio_id, []).append(patron)

    sin_asignar = Movimiento.query.filter(Movimiento.comercio_id.is_(None)).all()
    for mov in sin_asignar:
        desc = (mov.descripcion or '').strip()
        for regla_inc, patron_inc in reglas_incluir:
            # 1) Solo seguir si la inclusión matchea
            if not patron_inc.search(desc):
                continue
            # 2) Verificar exclusiones de este comercio
            patrones_excl = excl_por_comercio.get(regla_inc.comercio_id, [])
            if any(p_ex.search(desc) for p_ex in patrones_excl):
                # Está excluido de ESTE comercio → pruebo siguiente inclusión
                continue
            # 3) Coincidió inclusión y no hay exclusión → asignar y salir
            mov.comercio_id = regla_inc.comercio_id
            break

    db.session.commit()


def reclasificar_movimientos():
    """
    Igual que clasificar_movimientos, pero se aplica a **todos** los movimientos,
    reasignando comercios según las reglas.
    """
    reglas_excluir, reglas_incluir = cargar_reglas()

    excl_por_comercio = {}
    for regla, patron in reglas_excluir:
        excl_por_comercio.setdefault(regla.comercio_id, []).append(patron)

    todos = Movimiento.query.all()
    for mov in todos:
        desc = (mov.descripcion or '').strip()
        mov.comercio_id = None
        for regla_inc, patron_inc in reglas_incluir:
            if not patron_inc.search(desc):
                continue
            patrones_excl = excl_por_comercio.get(regla_inc.comercio_id, [])
            if any(p_ex.search(desc) for p_ex in patrones_excl):
                continue
            mov.comercio_id = regla_inc.comercio_id
            break

    db.session.commit()


def previsualizar_clasificacion(movimientos):
    """
    Dada una lista de objetos Movimiento (no persistidos),
    devuelve una lista de tuplas (movimiento, comercio_id_asignado o None).
    """
    reglas_excluir, reglas_incluir = cargar_reglas()
    excl_por_comercio = {}
    for regla, patron in reglas_excluir:
        excl_por_comercio.setdefault(regla.comercio_id, []).append(patron)

    resultados = []
    for mov in movimientos:
        desc = (mov.descripcion or '').strip()
        comercio_asignado = None
        for regla_inc, patron_inc in reglas_incluir:
            if not patron_inc.search(desc):
                continue
            patrones_excl = excl_por_comercio.get(regla_inc.comercio_id, [])
            if any(p_ex.search(desc) for p_ex in patrones_excl):
                continue
            comercio_asignado = regla_inc.comercio_id
            break
        resultados.append((mov, comercio_asignado))

    return resultados
