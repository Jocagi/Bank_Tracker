from datetime import datetime
from xml.etree import ElementTree as ET


def _safe_text(node):
    if node is None or node.text is None:
        return None
    text = node.text.strip()
    return text if text else None


def _safe_float(value):
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _safe_datetime(value):
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None

    # FEL usa formatos ISO con y sin fracciones de segundo.
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def parse_factura_fel_xml(filepath):
    """
    Parsea un XML FEL (GTDocumento) y retorna un dict con:
    - factura: campos generales
    - detalles: lista de items de la factura
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    ns = {
        'dte': 'http://www.sat.gob.gt/dte/fel/0.2.0',
        'cfe': 'http://www.sat.gob.gt/face2/ComplementoFacturaEspecial/0.1.0',
    }

    datos_emision = root.find('.//dte:DatosEmision', ns)
    if datos_emision is None:
        raise ValueError('No se encontró el nodo DatosEmision en el XML FEL.')

    datos_generales = datos_emision.find('dte:DatosGenerales', ns)
    emisor = datos_emision.find('dte:Emisor', ns)
    receptor = datos_emision.find('dte:Receptor', ns)
    cert = root.find('.//dte:Certificacion', ns)
    numero_autorizacion = cert.find('dte:NumeroAutorizacion', ns) if cert is not None else None

    total_impuesto_iva = None
    for impuesto in datos_emision.findall('.//dte:TotalImpuesto', ns):
        if (impuesto.attrib.get('NombreCorto') or '').upper() == 'IVA':
            total_impuesto_iva = _safe_float(impuesto.attrib.get('TotalMontoImpuesto'))
            break

    retencion_isr = _safe_float(_safe_text(datos_emision.find('.//cfe:RetencionISR', ns)))
    retencion_iva = _safe_float(_safe_text(datos_emision.find('.//cfe:RetencionIVA', ns)))
    total_menos_retenciones = _safe_float(_safe_text(datos_emision.find('.//cfe:TotalMenosRetenciones', ns)))

    uuid = _safe_text(numero_autorizacion)
    if not uuid:
        raise ValueError('No se encontró UUID de factura (NumeroAutorizacion).')

    factura = {
        'uuid': uuid,
        'serie': numero_autorizacion.attrib.get('Serie') if numero_autorizacion is not None else None,
        'numero_autorizacion': numero_autorizacion.attrib.get('Numero') if numero_autorizacion is not None else None,
        'tipo_documento': datos_generales.attrib.get('Tipo') if datos_generales is not None else None,
        'fecha_emision': _safe_datetime(datos_generales.attrib.get('FechaHoraEmision')) if datos_generales is not None else None,
        'fecha_certificacion': _safe_datetime(_safe_text(cert.find('dte:FechaHoraCertificacion', ns)) if cert is not None else None),
        'moneda': datos_generales.attrib.get('CodigoMoneda') if datos_generales is not None else None,
        'emisor_nit': emisor.attrib.get('NITEmisor') if emisor is not None else None,
        'emisor_nombre': emisor.attrib.get('NombreEmisor') if emisor is not None else None,
        'receptor_id': receptor.attrib.get('IDReceptor') if receptor is not None else None,
        'receptor_nombre': receptor.attrib.get('NombreReceptor') if receptor is not None else None,
        'gran_total': _safe_float(_safe_text(datos_emision.find('dte:Totales/dte:GranTotal', ns))),
        'total_impuesto_iva': total_impuesto_iva,
        'retencion_isr': retencion_isr,
        'retencion_iva': retencion_iva,
        'total_menos_retenciones': total_menos_retenciones,
    }

    detalles = []
    for item in datos_emision.findall('dte:Items/dte:Item', ns):
        detalles.append({
            'numero_linea': item.attrib.get('NumeroLinea'),
            'descripcion': _safe_text(item.find('dte:Descripcion', ns)),
            'cantidad': _safe_float(_safe_text(item.find('dte:Cantidad', ns))),
            'unidad_medida': _safe_text(item.find('dte:UnidadMedida', ns)),
            'precio_unitario': _safe_float(_safe_text(item.find('dte:PrecioUnitario', ns))),
            'total_linea': _safe_float(_safe_text(item.find('dte:Total', ns))),
        })

    return {
        'factura': factura,
        'detalles': detalles,
    }
