from django.contrib import messages
from django.shortcuts import redirect
from django.db.models import ProtectedError
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.mixins import PermissionRequiredMixin as DjangoPermissionRequiredMixin

class StaffRequiredMixin:
    """
    Mixin que verifica si el usuario es miembro del staff.
    Si no es staff, redirige con mensaje de error.
    
    Uso:
        class BrandDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
            ...
    
    ¿POR QUÉ?
    Porque solo el personal autorizado (staff) debe poder
    eliminar registros. Un usuario normal puede ver y crear,
    pero no borrar información importante del sistema.
    
    ¿CÓMO FUNCIONA?
    1. El usuario intenta acceder a una vista protegida
    2. dispatch() se ejecuta ANTES que la vista
    3. Si user.is_staff es False → redirige con mensaje de error
    4. Si user.is_staff es True → ejecuta la vista normalmente
    """

    # URL a donde redirigir si no es staff
    # Se puede sobreescribir en cada vista
    staff_redirect_url = '/'
    staff_error_message = 'No tienes permiso para realizar esta acción. Se requiere acceso de personal (staff).'

    def dispatch(self, request, *args, **kwargs):
        """
        dispatch() es el primer método que se ejecuta en una CBV.
        Interceptamos aquí para verificar permisos ANTES de
        procesar la petición (GET o POST).
        """
        # Verificar si el usuario es staff
        if not request.user.is_staff:
            # Mostrar mensaje de error al usuario
            messages.error(request, self.staff_error_message)
            # Redirigir a la URL configurada
            return redirect(self.staff_redirect_url)

        # Si es staff, continuar con el flujo normal de la vista
        return super().dispatch(request, *args, **kwargs)

class ProtectedDeleteMixin:
    """
    Mixin que atrapa ProtectedError al eliminar en una DeleteView (CBV)
    y muestra un mensaje en vez de reventar con la pantalla de error.

    Uso:
        class ProductDeleteView(ProtectedDeleteMixin, LoginRequiredMixin, DeleteView):
            protected_message = 'No se puede eliminar el producto porque...'

    ¿POR QUÉ?
    Los campos con on_delete=PROTECT impiden borrar registros que tienen
    hijos asociados. Sin esto, Django muestra una pantalla de error técnica.
    El mixin convierte ese error en un mensaje amigable.

    ¿CÓMO FUNCIONA?
    1. Sobreescribe post() (lo que corre al confirmar el borrado)
    2. Intenta delete() dentro de un try
    3. Si salta ProtectedError → muestra mensaje rojo y redirige
    4. Si borra bien → mensaje verde y redirige
    """

    # Mensaje por defecto; cada vista puede sobreescribirlo
    protected_message = 'No se puede eliminar porque tiene registros asociados.'
    success_message = 'Eliminado correctamente.'

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            self.object.delete()
            messages.success(request, self.success_message)
        except ProtectedError:
            messages.error(request, self.protected_message)
        return redirect(self.get_success_url())

class GroupRequiredMixin:
    """
    Mixin que verifica si el usuario pertenece a alguno
    de los roles (grupos) indicados en group_required.

    Uso:
        class GroupListView(LoginRequiredMixin, GroupRequiredMixin, ListView):
            group_required = ['Administrador']
    """
    group_required = []        # Lista de roles permitidos
    group_redirect_url = '/'   # A dónde redirigir si no tiene el rol
    group_error_message = 'No tienes permiso para acceder a esta opción.'

    def dispatch(self, request, *args, **kwargs):
        # 1. Si no inició sesión -> al login
        if not request.user.is_authenticated:
            return redirect('login')

        # 2. El superusuario siempre pasa
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        # 3. ¿Pertenece a alguno de los roles permitidos?
        if request.user.groups.filter(name__in=self.group_required).exists():
            return super().dispatch(request, *args, **kwargs)

        # 4. No tiene el rol -> mensaje de error y redirección
        messages.error(request, self.group_error_message)
        return redirect(self.group_redirect_url)


class PermissionRequiredMixin(DjangoPermissionRequiredMixin):
    """
    Extiende el PermissionRequiredMixin de Django: en vez de un 403 crudo
    cuando el usuario ya inició sesión pero le falta el permiso, redirige
    con mensaje de error -- mismo patrón que StaffRequiredMixin/GroupRequiredMixin.
    El superusuario siempre pasa (comportamiento nativo de Django).

    Uso:
        class InvoiceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
            permission_required = 'billing.view_invoice'
            permission_redirect_url = '/invoices/'
    """
    permission_redirect_url = '/'
    permission_denied_message = 'No tienes permiso para realizar esta acción.'

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, self.get_permission_denied_message())
        return redirect(self.permission_redirect_url)