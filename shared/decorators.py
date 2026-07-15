import logging
from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

from shared.mixins import has_any_crud_permission

# Configurar logger para auditoría
# Los mensajes se guardan en la consola y pueden redirigirse a archivo
logger = logging.getLogger('audit')


def audit_action(action_name):
    """
    Decorador que registra las acciones del usuario para auditoría.
    
    Parámetros:
        action_name (str): Nombre de la acción a registrar.
                          Ejemplo: "CREATE_BRAND", "DELETE_PRODUCT"
    
    Uso:
        @login_required
        @audit_action("CREATE_BRAND")
        def brand_create(request):
            ...
    
    ¿POR QUÉ?
    Para tener un registro de quién hizo qué en el sistema.
    Si un producto es eliminado, puedes rastrear quién lo hizo.
    
    ¿CÓMO FUNCIONA?
    1. El usuario llama a la vista (ej: brand_create)
    2. El decorador intercepta ANTES de ejecutar la vista
    3. Registra: usuario, acción, fecha/hora, método HTTP, IP
    4. Ejecuta la vista normalmente
    5. Si el método es POST (envío de formulario), registra también
       que la acción fue completada
    """

    def decorator(view_func):
        @wraps(view_func)  # Preserva el nombre y docstring de la vista original
        def wrapper(request, *args, **kwargs):

            # Obtener datos del usuario y la petición
            user = request.user.username if request.user.is_authenticated else 'Anonymous'
            ip = request.META.get('REMOTE_ADDR', 'unknown')  # IP del usuario
            method = request.method  # GET o POST
            timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            path = request.path  # URL que visitó

            # Registrar la acción en el log
            logger.info(
                f'[AUDIT] {timestamp} | User: {user} | '
                f'Action: {action_name} | Method: {method} | '
                f'Path: {path} | IP: {ip}'
            )

            # También imprimir en consola para desarrollo
            print(
                f'\n[AUDIT] {timestamp} | User: {user} | '
                f'Action: {action_name} | Method: {method} | '
                f'Path: {path} | IP: {ip}'
            )

            # Ejecutar la vista original normalmente
            response = view_func(request, *args, **kwargs)

            # Si fue POST, registrar que la acción se completó
            if method == 'POST':
                print(f'[AUDIT] {timestamp} | COMPLETED: {action_name} by {user}')

            return response

        return wrapper
    return decorator


def permission_required_with_message(perm, redirect_url='/', error_message=None):
    """
    Igual que @permission_required de Django, pero en vez de un 403 crudo
    redirige con messages.error, el mismo patrón que usan
    StaffRequiredMixin/GroupRequiredMixin/PermissionRequiredMixin (shared/mixins.py).
    El superusuario siempre pasa (user.has_perm nativo de Django).

    Uso:
        @login_required
        @permission_required_with_message('billing.add_invoice', redirect_url='/invoices/')
        def invoice_create(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(perm):
                messages.error(
                    request,
                    error_message or 'No tienes permiso para realizar esta acción.'
                )
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def any_crud_permission_required(app_label, model_name, redirect_url='/', error_message=None):
    """
    Equivalente FBV de shared.mixins.AnyCrudPermissionRequiredMixin: exige
    que el usuario tenga AL MENOS UNO de los 4 permisos nativos
    (view/add/change/delete) sobre `app_label.model_name` -- lógica OR,
    no el AND que impondría encadenar varios @permission_required_with_message.

    Uso:
        @login_required
        @any_crud_permission_required('billing', 'invoice', redirect_url='/invoices/')
        def invoice_detail(request, pk):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not has_any_crud_permission(request.user, app_label, model_name):
                messages.error(
                    request,
                    error_message or 'No tienes permiso para acceder a esta sección.'
                )
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
