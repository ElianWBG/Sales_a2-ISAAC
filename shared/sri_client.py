"""Cliente HTTP para el microservicio de facturación SRI (multi-tenant).

Envía POST /api/v1/facturas/ y devuelve el dict de respuesta (202)
o None si el micro no está configurado o hay un error de red.
Fire-and-forget: si falla, la factura ya fue creada localmente.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def emitir_factura_sri(invoice) -> dict | None:
    base_url = getattr(settings, 'SRI_MICRO_URL', '').rstrip('/')
    if not base_url:
        return None

    api_key = getattr(settings, 'SRI_MICRO_API_KEY', '').strip()
    store_name = getattr(settings, 'SRI_STORE_NAME', 'nuestra tienda')
    logo_url = getattr(settings, 'SRI_LOGO_URL', '')

    tipo_pago_label = {
        'CONTADO':  invoice.metodo_pago or 'EFECTIVO',
        'CREDITO':  'CRÉDITO (CUOTAS)',
    }.get(invoice.tipo_pago, invoice.tipo_pago or '')

    customer = invoice.customer
    dni = customer.dni or '9999999999'
    if len(dni) == 13:
        tipo_id = '04'   # RUC
    elif len(dni) == 10 and dni.isdigit():
        tipo_id = '05'   # Cédula
    else:
        tipo_id = '06'   # Pasaporte

    items = [
        {
            'codigo':          str(d.product.pk),
            'descripcion':     d.product.name,
            'cantidad':        str(d.quantity),
            'precio_unitario': str(d.unit_price),
            'descuento':       '0',
            'codigo_iva':      '2',
        }
        for d in invoice.details.select_related('product').all()
    ]

    payload = {
        'cliente_identificacion':       dni,
        'cliente_tipo_identificacion':  tipo_id,
        'cliente_razon_social':         customer.full_name,
        'cliente_email':                customer.email or '',
        'cliente_direccion':            customer.address or '',
        'cliente_telefono':             customer.phone or '',
        'items':                        items,
        'store_name':                   store_name,
        'logo_url':                     logo_url,
        'tipo_pago_label':              tipo_pago_label,
        'factura_id_principal':         invoice.pk,
    }

    try:
        req = urllib.request.Request(
            f'{base_url}/api/v1/facturas/',
            data=json.dumps(payload).encode(),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            },
            method='POST',
        )
        timeout = getattr(settings, 'SRI_MICRO_TIMEOUT', 30)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            logger.info(
                'Factura %s enviada al micro SRI → id=%s estado=%s',
                invoice.pk, result.get('id'), result.get('estado'),
            )
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        logger.exception('Error HTTP %s del micro SRI para factura %s: %s', e.code, invoice.pk, body)
    except Exception as e:
        logger.exception('Error llamando al micro SRI para factura %s: %s', invoice.pk, e)
    return None
