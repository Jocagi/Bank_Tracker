from flask import request, url_for

SORT_ASC = 'asc'
SORT_DESC = 'desc'


def resolver_orden(columnas, clave_default, direccion_default=SORT_ASC):
    """Lee ?sort= y ?dir= de la URL; valores inválidos caen al default."""
    clave = request.args.get('sort', '')
    if clave not in columnas:
        return clave_default, direccion_default
    direccion = request.args.get('dir', '')
    if direccion not in (SORT_ASC, SORT_DESC):
        direccion = direccion_default
    return clave, direccion


def aplicar_orden(query, columnas, clave, direccion, desempate):
    expresion = columnas[clave]
    principal = expresion.asc() if direccion == SORT_ASC else expresion.desc()
    return query.order_by(principal, desempate.desc())


def construir_enlaces_orden(endpoint, columnas, clave, direccion):
    """Enlaces de encabezado: conservan filtros y reinician en página 1."""
    base = {k: v for k, v in request.args.items() if k not in ('page', 'sort', 'dir')}
    enlaces = {}
    for col in columnas:
        if col == clave:
            siguiente = SORT_DESC if direccion == SORT_ASC else SORT_ASC
            indicador = ' ▲' if direccion == SORT_ASC else ' ▼'
        else:
            siguiente = SORT_ASC
            indicador = ''
        enlaces[col] = {
            'href': url_for(endpoint, **base, sort=col, dir=siguiente, page=1),
            'indicator': indicador,
        }
    return enlaces
