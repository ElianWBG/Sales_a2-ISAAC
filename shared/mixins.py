from django.contrib import messages
from django.shortcuts import redirect
from django.db.models import ProtectedError
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
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


class SuccessUrlPreservePageMixin:
    """
    Mixin para DeleteView (CBV): al eliminar un registro desde una lista
    paginada, conserva el número de página en el redirect en vez de volver
    siempre a la página 1.

    Requiere que el template de confirmación reenvíe `page` como campo
    oculto del form (leído del `?page=` con el que se llegó a esa
    pantalla) -- ver brand_confirm_delete.html y similares.

    Uso (colocar ANTES de DeleteView en el MRO, junto a los demás mixins):
        class ProductDeleteView(SuccessUrlPreservePageMixin, ProtectedDeleteMixin,
                                 LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
            success_url = reverse_lazy('billing:product_list')
    """
    def get_success_url(self):
        url = super().get_success_url()
        page = self.request.POST.get('page') or self.request.GET.get('page')
        if page and page.isdigit():
            url = f'{url}?page={page}'
        return url


class GracefulPaginationMixin:
    """
    Mixin para ListView: si el `?page=N` solicitado ya no existe (ej. se
    acaba de eliminar el único registro que quedaba en esa página, y
    SuccessUrlPreservePageMixin/redirect_preserving_page redirigieron ahí),
    cae a la última página válida en vez de tirar un 404.

    Reimplementa MultipleObjectMixin.paginate_queryset (mismo comportamiento
    que Django salvo en el manejo de página inválida): en vez de levantar
    Http404, recorta el número de página al rango [1, num_pages].

    Uso (colocar en cualquier posición antes de ListView en el MRO):
        class ProductListView(GracefulPaginationMixin, ExportMixin,
                               LoginRequiredMixin, PermissionRequiredMixin, ListView):
            paginate_by = 3
    """
    def paginate_queryset(self, queryset, page_size):
        paginator = self.get_paginator(
            queryset, page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        page_kwarg = self.page_kwarg
        page_param = self.kwargs.get(page_kwarg) or self.request.GET.get(page_kwarg) or 1

        try:
            page_number = int(page_param)
        except (TypeError, ValueError):
            page_number = paginator.num_pages if page_param == 'last' else 1

        page_number = max(1, min(page_number, paginator.num_pages))
        page = paginator.page(page_number)
        return (paginator, page, page.object_list, page.has_other_pages())


def has_any_crud_permission(user, app_label, model_name):
    """
    True si `user` tiene AL MENOS UNO de los 4 permisos nativos de Django
    (view/add/change/delete) sobre `app_label.model_name`.

    Django no ofrece esto de fábrica: PermissionRequiredMixin, cuando se
    le pasan varios permisos, exige TODOS (AND vía user.has_perms()). Acá
    se necesita lo contrario -- que baste con cualquiera de los 4 (OR) --
    así que se arma a mano con any(). user.has_perm() ya deja pasar al
    superusuario automáticamente, no hace falta chequearlo aparte.

    Fase 2b: reemplaza el acceso abierto temporal de la Fase 2a en las
    22 vistas de billing/purchasing/creditos_ventas/creditos_compras que
    antes bloqueaban con un único view_<modelo> (AnyCrudPermissionRequiredMixin,
    any_crud_permission_required) y en los links del navbar (base.html).
    """
    return any(
        user.has_perm(f'{app_label}.{action}_{model_name}')
        for action in ('view', 'add', 'change', 'delete')
    )


class AnyCrudPermissionRequiredMixin:
    """
    Mixin para CBV (ListView/DetailView): exige que el usuario tenga AL
    MENOS UNO de los 4 permisos nativos (view/add/change/delete) sobre
    `self.model` -- lógica OR, no la lógica AND de PermissionRequiredMixin.

    Deriva app_label/model_name de `self.model` automáticamente; solo
    hace falta sobreescribir get_permission_app_label_model() si la vista
    no tiene `model` seteado directo (no es el caso de ninguna de las 22
    vistas de billing/purchasing/creditos_ventas/creditos_compras).

    Uso (colocar DESPUÉS de LoginRequiredMixin en el MRO, mismo orden que
    ya se usaba con PermissionRequiredMixin):
        class ProductListView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
            model = Product
    """
    permission_redirect_url = '/'
    permission_denied_message = 'No tienes permiso para acceder a esta sección.'

    def get_permission_app_label_model(self):
        opts = self.model._meta
        return opts.app_label, opts.model_name

    def has_permission(self):
        app_label, model_name = self.get_permission_app_label_model()
        return has_any_crud_permission(self.request.user, app_label, model_name)

    def dispatch(self, request, *args, **kwargs):
        if not self.has_permission():
            messages.error(request, self.permission_denied_message)
            return redirect(self.permission_redirect_url)
        return super().dispatch(request, *args, **kwargs)


def redirect_preserving_page(request, url_name):
    """
    Igual que SuccessUrlPreservePageMixin, pero para vistas basadas en
    función (FBV): redirige a `url_name` conservando el `?page=N` leído
    del POST/GET de la petición, en vez de volver siempre a la página 1.

    Uso:
        return redirect_preserving_page(request, 'billing:brand_list')
    """
    url = reverse(url_name)
    page = request.POST.get('page') or request.GET.get('page')
    if page and page.isdigit():
        url = f'{url}?page={page}'
    return redirect(url)