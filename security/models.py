from django.conf import settings
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
