"""
Cliente mínimo para la REST API v2 de PayPal (Checkout: crear orden / capturar).

No usamos el SDK oficial de PayPal porque está prácticamente abandonado;
esto son 3 llamadas HTTP simples con la librería `requests`, más fácil de
entender y de depurar para el proyecto.

Flujo típico (Invoice de contado o pago de una CuotaVenta):
    1. El usuario elige "Pagar con PayPal" -> la vista llama a
       create_paypal_order(monto) y devuelve el `id` de la orden al
       frontend (lo usa el botón de PayPal para abrir el checkout).
    2. El cliente aprueba el pago en la ventana de PayPal.
    3. El frontend avisa a la vista que la orden fue aprobada -> la vista
       llama a capture_paypal_order(order_id) para confirmar el cobro y
       guarda paypal_capture_id / paypal_status / paypal_payer_email.
"""

import requests
from django.conf import settings


class PayPalError(Exception):
    """Se lanza cuando PayPal responde con un error (credenciales, orden inválida, etc.)."""
    pass


def _base_url():
    if settings.PAYPAL_MODE == 'live':
        return 'https://api-m.paypal.com'
    return 'https://api-m.sandbox.paypal.com'


def _get_access_token():
    """
    PayPal usa OAuth2 client_credentials: con el Client ID + Secret pedimos
    un token de acceso de corta duración, que se usa en cada llamada
    siguiente. No lo cacheamos (el proyecto es de bajo volumen); si el
    tráfico creciera, esto se podría guardar en cache unos minutos.
    """
    url = f'{_base_url()}/v1/oauth2/token'
    response = requests.post(
        url,
        headers={'Accept': 'application/json', 'Accept-Language': 'en_US'},
        data={'grant_type': 'client_credentials'},
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        timeout=15,
    )
    if response.status_code != 200:
        raise PayPalError(f'No se pudo autenticar con PayPal: {response.text}')
    return response.json()['access_token']


def create_paypal_order(amount, currency='USD', description=''):
    """
    Crea una orden de PayPal por `amount` (Decimal o str) y devuelve el
    dict completo de la respuesta. Lo importante para el frontend es
    response['id'] (el order_id que necesita el botón de PayPal).
    """
    token = _get_access_token()
    url = f'{_base_url()}/v2/checkout/orders'
    payload = {
        'intent': 'CAPTURE',
        'purchase_units': [{
            'amount': {
                'currency_code': currency,
                'value': f'{float(amount):.2f}',
            },
            'description': description[:127],  # PayPal limita este campo
        }],
    }
    response = requests.post(
        url,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        },
        json=payload,
        timeout=15,
    )
    if response.status_code not in (200, 201):
        raise PayPalError(f'No se pudo crear la orden de PayPal: {response.text}')
    return response.json()


def capture_paypal_order(order_id):
    """
    Confirma (captura) el pago de una orden ya aprobada por el cliente en
    el checkout de PayPal. Devuelve el dict completo de la respuesta.

    Del resultado normalmente interesan:
      - data['status']  ->  'COMPLETED' si todo salió bien
      - data['purchase_units'][0]['payments']['captures'][0]['id']  -> capture_id
      - data['payer']['email_address']  -> correo del pagador
    """
    token = _get_access_token()
    url = f'{_base_url()}/v2/checkout/orders/{order_id}/capture'
    response = requests.post(
        url,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        },
        timeout=15,
    )
    if response.status_code not in (200, 201):
        raise PayPalError(f'No se pudo capturar el pago de PayPal: {response.text}')
    return response.json()


def extract_capture_data(capture_response):
    """
    Saca de la respuesta de capture_paypal_order() los 3 datos que
    guardamos en el modelo (capture_id, status, correo del pagador),
    con manejo defensivo por si PayPal cambia la forma de la respuesta.
    """
    status = capture_response.get('status')
    capture_id = None
    try:
        capture_id = (
            capture_response['purchase_units'][0]['payments']['captures'][0]['id']
        )
    except (KeyError, IndexError):
        pass
    payer_email = capture_response.get('payer', {}).get('email_address')
    return {
        'capture_id': capture_id,
        'status': status,
        'payer_email': payer_email,
    }