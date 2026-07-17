"""
Utilidades centralizadas de correo/mensajería del sistema.

Todas las vistas que necesiten mandar un correo (registro de usuario,
factura al cliente, etc.) importan funciones de aquí, en vez de armar el
mensaje suelto en cada view. Así hay un solo lugar que sabe "cómo se ve"
cada tipo de correo del sistema.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.urls import reverse

from shared.formatting import money

logger = logging.getLogger(__name__)


def send_welcome_email_with_temp_password(user, temp_password, request=None):
    """
    Correo que recibe un usuario cuando el Administrador crea su cuenta
    manualmente (UserCreateView). Incluye usuario + contraseña temporal,
    y le avisa que debe cambiarla al entrar.

    `request` es opcional -- si se pasa (UserCreateView sí lo tiene), el
    botón "Iniciar sesión" del HTML usa una URL absoluta; si no, cae a la
    ruta relativa (funciona igual al hacer click desde el cliente de correo).
    """
    if not user.email:
        return False

    subject = 'Bienvenido al Sistema de Ventas - Tus credenciales de acceso'
    nombre = user.first_name or user.username
    login_path = reverse('login')
    login_url = request.build_absolute_uri(login_path) if request else login_path

    text_message = (
        f'Hola {nombre},\n\n'
        f'Se creó una cuenta para ti en el Sistema de Ventas.\n\n'
        f'Usuario:               {user.username}\n'
        f'Contraseña temporal:   {temp_password}\n\n'
        f'Por seguridad, el sistema te va a pedir cambiar esta contraseña '
        f'la primera vez que inicies sesión.\n\n'
        f'Iniciar sesión: {login_url}\n\n'
        f'Si no esperabas este correo, contacta al administrador del sistema.'
    )
    html_message = f'''\
<div style="font-family: Arial, Helvetica, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #dee2e6; border-radius: 8px; overflow: hidden;">
  <div style="background: #1a56db; padding: 20px 24px;">
    <h1 style="margin: 0; color: #ffffff; font-size: 20px;">Sistema de Ventas</h1>
  </div>
  <div style="padding: 24px;">
    <p style="font-size: 15px; color: #212529;">Hola {nombre},</p>
    <p style="font-size: 15px; color: #212529;">Se creó una cuenta para ti en el Sistema de Ventas. Estas son tus credenciales de acceso:</p>

    <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 16px 20px; margin: 20px 0;">
      <p style="margin: 0 0 8px 0; font-size: 14px; color: #495057;">Usuario</p>
      <p style="margin: 0 0 16px 0; font-family: 'Courier New', Courier, monospace; font-size: 16px; color: #212529;">{user.username}</p>
      <p style="margin: 0 0 8px 0; font-size: 14px; color: #495057;">Contraseña temporal</p>
      <p style="margin: 0; font-family: 'Courier New', Courier, monospace; font-size: 16px; color: #212529;">{temp_password}</p>
    </div>

    <div style="background: #fff3cd; border: 1px solid #ffe69c; border-radius: 8px; padding: 14px 18px; margin: 20px 0;">
      <p style="margin: 0; font-size: 14px; color: #664d03;"><strong>Aviso de seguridad:</strong> por tu seguridad, el sistema te va a pedir cambiar esta contraseña la primera vez que inicies sesión.</p>
    </div>

    <div style="text-align: center; margin: 28px 0 8px 0;">
      <a href="{login_url}" style="background: #1a56db; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 6px; font-size: 15px; font-weight: bold; display: inline-block;">Iniciar sesión</a>
    </div>
  </div>
  <div style="border-top: 1px solid #dee2e6; padding: 16px 24px;">
    <p style="margin: 0; font-size: 12px; color: #868e96;">Si no esperabas este correo, contacta al administrador del sistema.</p>
  </div>
</div>
'''
    try:
        email = EmailMultiAlternatives(
            subject, text_message,
            settings.DEFAULT_FROM_EMAIL, [user.email],
        )
        email.attach_alternative(html_message, 'text/html')
        sent = email.send(fail_silently=False)
        return bool(sent)
    except Exception:
        logger.exception('Error enviando email de bienvenida a %s', user.email)
        return False


def send_invoice_email(invoice, pdf_bytes, xml_bytes=None):
    """
    Envía la factura al correo del cliente, con el PDF adjunto y, si ya se
    consiguió (ver shared.sri_client.esperar_xml_factura_sri), el XML del
    comprobante electrónico autorizado por el SRI -- en un solo mensaje.
    Devuelve False (sin lanzar error) si el cliente no tiene correo
    registrado, para que la vista pueda avisar sin romperse.
    """
    customer_email = getattr(invoice.customer, 'email', None)
    if not customer_email:
        return False

    subject = f'Tu factura #{invoice.id} - Sistema de Ventas'
    body = f'Hola {invoice.customer.full_name},\n\n'
    if xml_bytes:
        body += (
            f'Adjunto encontrarás tu factura #{invoice.id}, el comprobante '
            f'electrónico autorizado por el SRI (XML), por un total de '
            f'{money(invoice.total)}.\n\n'
        )
    else:
        body += (
            f'Adjunto encontrarás tu factura #{invoice.id} por un total de '
            f'{money(invoice.total)}.\n\n'
        )
        # El comprobante electrónico (XML) solo se emite para ventas de
        # CONTADO (emitir_factura_sri se llama al confirmarse el pago en
        # efectivo/transferencia o tras capturar PayPal -- ver
        # billing/views.py). Las ventas a CRÉDITO nunca pasan por el
        # microservicio SRI, así que no corresponde prometer un correo que
        # no va a llegar.
        #
        # LIMITACIÓN CONOCIDA: emitir_factura_sri() manda enviar_email=False
        # para que el micro SRI no duplique el correo -- así que si el SRI
        # no autorizó a tiempo (esperar_xml_factura_sri agotó los
        # intentos), este texto promete un correo aparte que en realidad
        # NUNCA va a llegar (no hay reintento en segundo plano/cron). Es
        # una limitación aceptada por ahora, no un bug.
        if invoice.tipo_pago != 'CREDITO':
            body += (
                'El comprobante electrónico (XML) te llegará en un correo '
                'separado una vez autorizado por el SRI.\n\n'
            )
    body += '¡Gracias por tu compra!'
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer_email],
    )
    email.attach(f'factura_{invoice.id}.pdf', pdf_bytes, 'application/pdf')
    if xml_bytes:
        email.attach(f'factura_{invoice.id}.xml', xml_bytes, 'application/xml')
    try:
        return bool(email.send(fail_silently=False))
    except Exception:
        logger.exception('Error enviando email para %s a %s', subject, email.to)
        return False


def send_purchase_email(purchase, pdf_bytes):
    """
    Envía la orden de compra al correo del proveedor, con el PDF adjunto.
    Devuelve False (sin lanzar error) si el proveedor no tiene correo
    registrado, para que la vista pueda avisar sin romperse.
    """
    supplier_email = getattr(purchase.supplier, 'email', None)
    if not supplier_email:
        return False

    subject = f'Orden de Compra #{purchase.id} - Sistema de Ventas'
    body = (
        f'Hola {purchase.supplier.name},\n\n'
        f'Adjunto encontrarás la orden de compra #{purchase.id} por un total de '
        f'{money(purchase.total)}.\n\n'
        f'Saludos.'
    )
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[supplier_email],
    )
    email.attach(f'compra_{purchase.id}.pdf', pdf_bytes, 'application/pdf')
    try:
        return bool(email.send(fail_silently=False))
    except Exception:
        logger.exception('Error enviando email para %s a %s', subject, email.to)
        return False
