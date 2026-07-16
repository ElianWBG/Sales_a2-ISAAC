from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import models


class PerfilUsuario(models.Model):
    """
    Extiende al User de Django con datos propios de seguridad que no
    caben en el modelo base (no lo modificamos directamente porque es
    de Django, no nuestro).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil'
    )
    must_change_password = models.BooleanField(
        default=True,
        verbose_name='Debe cambiar la contraseña',
        help_text='Se activa cuando el Administrador crea la cuenta con una contraseña temporal.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuario'

    def __str__(self):
        return f'Perfil de {self.user.username}'


class RoleDefaultPermissions(models.Model):
    """
    "Default" guardado a mano para un rol CUSTOM (creado con "+ Nuevo rol",
    fuera de los 6 fijos de setup_roles.py -- esos usan el código como
    única fuente de verdad, ver security.views.FIXED_ROLE_NAMES). Guarda
    una fotografía completa de los permisos del rol al momento de
    "Guardar como predeterminado" (botón en RolePermissionsView), para
    poder volver a ese estado después con "Permisos predeterminados" sin
    depender de que alguien recuerde a mano qué tenía marcado.
    """
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name='default_permissions')
    permissions = models.ManyToManyField(Permission, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Permisos predeterminados de rol'
        verbose_name_plural = 'Permisos predeterminados de roles'

    def __str__(self):
        return f'Default de {self.group.name}'
