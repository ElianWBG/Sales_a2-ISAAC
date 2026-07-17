"""Cliente HTTP para el microservicio de facturación SRI (multi-tenant).

Envía POST /api/v1/facturas/ y devuelve el dict de respuesta (202)
o None si el micro no está configurado o hay un error de red.
Fire-and-forget: si falla, la factura ya fue creada localmente.

El POST manda enviar_email=False -- el micro autoriza la factura ante el
SRI pero NO manda su propio correo con el XML; Django arma un solo correo
combinado (PDF + XML) vía esperar_xml_factura_sri() + shared/emails.py.
"""
import base64
import json
import logging
import time
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
        'enviar_email':                 False,
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


def consultar_factura_sri(sri_id) -> dict | None:
    """
    GET /api/v1/facturas/<sri_id>/ -- devuelve el dict de respuesta (incluye
    'estado' y 'xml', este último en base64 y null hasta que el SRI autorice)
    o None si el micro no está configurado, sri_id es None, o hay error.
    """
    base_url = getattr(settings, 'SRI_MICRO_URL', '').rstrip('/')
    if not base_url or not sri_id:
        return None

    api_key = getattr(settings, 'SRI_MICRO_API_KEY', '').strip()
    try:
        req = urllib.request.Request(
            f'{base_url}/api/v1/facturas/{sri_id}/',
            headers={'Authorization': f'Bearer {api_key}'},
            method='GET',
        )
        timeout = getattr(settings, 'SRI_MICRO_TIMEOUT', 30)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        logger.exception('Error HTTP %s consultando factura SRI %s: %s', e.code, sri_id, body)
    except Exception as e:
        logger.exception('Error consultando factura SRI %s: %s', sri_id, e)
    return None


def esperar_xml_factura_sri(sri_id, intentos=None, espera_segundos=None) -> bytes | None:
    """
    Hace polling a consultar_factura_sri() esperando a que el campo `xml`
    deje de ser null (factura AUTORIZADA por el SRI). Devuelve los bytes del
    XML ya decodificados de base64, o None si sri_id es None, el micro no
    está configurado, o no autorizó dentro de la ventana de intentos.

    Pensado para llamarse desde un hilo aparte (ver billing/views.py):
    bloquea el hilo que lo llama durante `intentos * espera_segundos`
    segundos como máximo, así que nunca debe llamarse directo desde el hilo
    de la request/respuesta HTTP.

    LIMITACIÓN CONOCIDA: emitir_factura_sri() manda enviar_email=False, así
    que si el SRI no autoriza dentro de esta ventana, el correo sale solo
    con el PDF (ver shared/emails.py::send_invoice_email) y el cliente NO
    va a recibir ningún otro correo automático con el XML más adelante --
    no hay reintento en segundo plano ni cron para este caso, es una
    limitación aceptada, no un bug.
    """
    if not sri_id:
        return None
    intentos = intentos if intentos is not None else getattr(settings, 'SRI_POLL_INTENTOS', 6)
    espera_segundos = espera_segundos if espera_segundos is not None else getattr(settings, 'SRI_POLL_INTERVALO_SEGUNDOS', 1.5)

    for intento in range(1, intentos + 1):
        data = consultar_factura_sri(sri_id)
        xml_b64 = data.get('xml') if data else None
        if xml_b64:
            try:
                return base64.b64decode(xml_b64)
            except Exception:
                logger.exception('XML de factura SRI %s vino en base64 inválido', sri_id)
                return None
        if intento < intentos:
            time.sleep(espera_segundos)

    logger.info(
        'Factura SRI %s no autorizó dentro de %s intentos (cada %ss); '
        'el correo sale sin el XML adjunto.', sri_id, intentos, espera_segundos,
    )
    return None
