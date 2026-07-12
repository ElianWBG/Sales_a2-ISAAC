"""
Utilidades centralizadas de correo/mensajería del sistema.

Todas las vistas que necesiten mandar un correo (registro de usuario,
factura al cliente, etc.) importan funciones de aquí, en vez de armar el
mensaje suelto en cada view. Así hay un solo lugar que sabe "cómo se ve"
cada tipo de correo del sistema.
"""

from django.conf import settings
from django.core.mail import EmailMessage, send_mail


def send_welcome_email_with_temp_password(user, temp_password):
    """
    Correo que recibe un usuario cuando el Administrador crea su cuenta
    manualmente (UserCreateView). Incluye usuario + contraseña temporal,
    y le avisa que debe cambiarla al entrar.
    """
    if not user.email:
        return False

    subject = 'Bienvenido al Sistema de Ventas - Tus credenciales de acceso'
    message = (
        f'Hola {user.first_name or user.username},\n\n'
        f'Se creó una cuenta para ti en el Sistema de Ventas.\n\n'
        f'Usuario:               {user.username}\n'
        f'Contraseña temporal:   {temp_password}\n\n'
        f'Por seguridad, el sistema te va a pedir cambiar esta contraseña '
        f'la primera vez que inicies sesión.\n\n'
        f'Si no esperabas este correo, contacta al administrador del sistema.'
    )
    send_mail(
        subject, message,
        settings.DEFAULT_FROM_EMAIL, [user.email],
        fail_silently=False,
    )
    return True


def send_invoice_email(invoice, pdf_bytes):
    """
    Envía la factura al correo del cliente, con el PDF adjunto.
    Devuelve False (sin lanzar error) si el cliente no tiene correo
    registrado, para que la vista pueda avisar sin romperse.
    """
    customer_email = getattr(invoice.customer, 'email', None)
    if not customer_email:
        return False

    subject = f'Tu factura #{invoice.id} - Sistema de Ventas'
    body = (
        f'Hola {invoice.customer.full_name},\n\n'
        f'Adjunto encontrarás tu factura #{invoice.id} por un total de '
        f'${invoice.total}.\n\n'
        f'¡Gracias por tu compra!'
    )
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[customer_email],
    )
    email.attach(f'factura_{invoice.id}.pdf', pdf_bytes, 'application/pdf')
    email.send(fail_silently=False)
    return True
