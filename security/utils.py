import re
import unicodedata

from django.contrib.auth.models import User


def _normalizar(texto):
    """Minúsculas, sin tildes/ñ ni caracteres que no sean letras o dígitos."""
    sin_tildes = ''.join(
        c for c in unicodedata.normalize('NFKD', texto or '')
        if not unicodedata.combining(c)
    )
    return re.sub(r'[^a-zA-Z0-9]', '', sin_tildes).lower()


def _generar_username_base(first_name, last_name):
    """
    Primera letra del primer nombre + primer apellido + primera letra del
    segundo apellido (ej. "Isaac Anthony", "Silva Quiroz" -> "isilvaq").
    Si solo hay un apellido: primera letra del nombre + apellido completo
    (ej. "Isaac", "Torres" -> "itorres").
    """
    nombres = (first_name or '').split()
    apellidos = (last_name or '').split()

    inicial_nombre = _normalizar(nombres[0])[:1] if nombres else ''

    if len(apellidos) >= 2:
        primer_apellido = _normalizar(apellidos[0])
        inicial_segundo_apellido = _normalizar(apellidos[1])[:1]
        return f'{inicial_nombre}{primer_apellido}{inicial_segundo_apellido}'

    apellido_completo = _normalizar(apellidos[0]) if apellidos else ''
    return f'{inicial_nombre}{apellido_completo}'


def generar_username(first_name, last_name):
    """Username único estilo universidad, agregando 2, 3, ... si ya existe."""
    base = _generar_username_base(first_name, last_name)

    username = base
    sufijo = 2
    while User.objects.filter(username=username).exists():
        username = f'{base}{sufijo}'
        sufijo += 1
    return username


def es_ultimo_administrador_activo(user):
    """True si `user` es el único usuario activo con rol Administrador."""
    otros_admins = User.objects.filter(
        groups__name='Administrador', is_active=True
    ).exclude(pk=user.pk)
    return not otros_admins.exists()
