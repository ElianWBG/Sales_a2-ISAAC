from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """
    Si el usuario logueado tiene perfil.must_change_password = True
    (porque el Administrador le creó la cuenta con clave temporal),
    lo obliga a pasar por 'password_change' antes de usar cualquier
    otra parte del sistema.

    ALLOWLIST: rutas que sí puede visitar mientras tiene la clave
    temporal (cambiar contraseña, cerrar sesión, estáticos/media).
    """

    ALLOWED_PATH_PREFIXES = (
        '/accounts/password_change/',
        '/accounts/logout/',
        '/static/',
        '/media/',
        '/admin/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)

        if user and user.is_authenticated and not user.is_superuser:
            perfil = getattr(user, 'perfil', None)
            if perfil and perfil.must_change_password:
                if not any(request.path.startswith(p) for p in self.ALLOWED_PATH_PREFIXES):
                    return redirect(reverse('password_change'))

        return self.get_response(request)
