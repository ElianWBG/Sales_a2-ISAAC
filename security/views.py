import secrets
import string

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from shared.mixins import GroupRequiredMixin
from shared.emails import send_welcome_email_with_temp_password
from .forms import CambiarPasswordForm, UserUpdateForm, GroupForm, PermissionForm, AdminUserCreateForm
from .models import PerfilUsuario
from .utils import generar_username


# === MIXIN BASE: SOLO ADMINISTRADOR ===

class AdminOnlyMixin(LoginRequiredMixin, GroupRequiredMixin):
    """Combina login + rol Administrador (el superusuario siempre pasa)."""
    group_required = ['Administrador']
    group_redirect_url = '/'


# === AUTENTICACIÓN (CBV) ===
# El auto-registro público fue eliminado: los usuarios ahora se crean
# únicamente por el Administrador desde "Usuarios" (UserCreateView).

class SecurityLoginView(LoginView):
    """Login con CBV. Reutiliza el template de la PARTE 9."""
    template_name = 'registration/login.html'


class SecurityLogoutView(LogoutView):
    """Logout con CBV. Redirige según LOGOUT_REDIRECT_URL."""
    pass


# === USUARIOS (solo Administrador) ===

class UserListView(AdminOnlyMixin, ListView):
    model = User
    template_name = 'security/user_list.html'
    context_object_name = 'items'


def _generar_password_temporal(length=10):
    """Contraseña temporal legible: letras + dígitos, fácil de transcribir."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class UserCreateView(AdminOnlyMixin, CreateView):
    """
    El Administrador crea la cuenta de otra persona (ej. un nuevo Vendedor).
    Es la única forma de crear usuarios (no hay auto-registro público):
      1. Genera una contraseña temporal.
      2. Marca el perfil con must_change_password=True.
      3. Envía usuario + contraseña temporal por correo.
      4. En el primer login, ForcePasswordChangeMiddleware lo obliga a
         cambiarla antes de poder usar el sistema.
    """
    form_class = AdminUserCreateForm
    template_name = 'security/user_create_form.html'
    success_url = reverse_lazy('security:user_list')

    def form_valid(self, form):
        temp_password = _generar_password_temporal()

        user = form.save(commit=False)
        user.username = generar_username(user.first_name, user.last_name)
        user.set_password(temp_password)
        user.save()
        user.groups.add(form.cleaned_data['role'])

        PerfilUsuario.objects.create(user=user, must_change_password=True)

        enviado = send_welcome_email_with_temp_password(user, temp_password)

        if enviado:
            messages.success(
                self.request,
                f'Usuario "{user.username}" creado. Se envió la contraseña '
                f'temporal a {user.email}.'
            )
        else:
            # No tenía correo (no debería pasar, el form lo exige) -> se
            # muestra aquí como respaldo para no dejar al admin a ciegas.
            messages.warning(
                self.request,
                f'Usuario "{user.username}" creado. Contraseña temporal '
                f'(no se pudo enviar por correo): {temp_password}'
            )
        return redirect(self.success_url)


class UserUpdateView(AdminOnlyMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'security/user_form.html'
    success_url = reverse_lazy('security:user_list')


class UserDeleteView(AdminOnlyMixin, DeleteView):
    model = User
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:user_list')


# === ROLES / GROUP (solo Administrador) ===

class GroupListView(AdminOnlyMixin, ListView):
    model = Group
    template_name = 'security/group_list.html'
    context_object_name = 'items'


class GroupCreateView(AdminOnlyMixin, CreateView):
    model = Group
    form_class = GroupForm
    template_name = 'security/group_form.html'
    success_url = reverse_lazy('security:group_list')


class GroupUpdateView(AdminOnlyMixin, UpdateView):
    model = Group
    form_class = GroupForm
    template_name = 'security/group_form.html'
    success_url = reverse_lazy('security:group_list')


class GroupDeleteView(AdminOnlyMixin, DeleteView):
    model = Group
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:group_list')


# === PERMISOS / PERMISSION (solo Administrador) ===

class PermissionListView(AdminOnlyMixin, ListView):
    model = Permission
    template_name = 'security/permission_list.html'
    context_object_name = 'items'
    queryset = Permission.objects.select_related('content_type').order_by(
        'content_type__app_label', 'content_type__model', 'codename'
    )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Traduce el nombre de cada permiso ("Can view Empleado" -> "Puede ver
        # Empleado") reusando los mismos diccionarios de la matriz de roles,
        # sin tocar el campo `name` real que guarda Django en la BD.
        for p in ctx['items']:
            action = p.codename.split('_')[0]
            if action in ACTION_DISPLAY:
                model_label = MODEL_NAME_DISPLAY.get(
                    p.content_type.model, p.content_type.model.capitalize()
                )
                p.nombre_es = f'Puede {ACTION_DISPLAY[action].lower()} {model_label}'
            else:
                p.nombre_es = p.name
        return ctx


class PermissionCreateView(AdminOnlyMixin, CreateView):
    model = Permission
    form_class = PermissionForm
    template_name = 'security/permission_form.html'
    success_url = reverse_lazy('security:permission_list')


class PermissionUpdateView(AdminOnlyMixin, UpdateView):
    model = Permission
    form_class = PermissionForm
    template_name = 'security/permission_form.html'
    success_url = reverse_lazy('security:permission_list')


class PermissionDeleteView(AdminOnlyMixin, DeleteView):
    model = Permission
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:permission_list')


# === MATRIZ DE PERMISOS POR ROL (solo Administrador) ===

# Nombre amigable para cada app (módulo) del sistema.
APP_LABEL_DISPLAY = {
    'billing': 'Facturación e Inventario',
    'purchasing': 'Compras',
    'empleados': 'Empleados',
    'categoria': 'Categorías de Gasto',
    'departamento': 'Departamentos',
    'cobros': 'Cobros',
    'pagos': 'Pagos',
    'security': 'Seguridad',
    'auth': 'Usuarios y Roles',
}

# Nombre amigable para cada modelo (si no está aquí, se usa el nombre tal cual).
MODEL_NAME_DISPLAY = {
    'brand': 'Marcas',
    'productgroup': 'Grupos de Productos',
    'supplier': 'Proveedores',
    'product': 'Productos',
    'customer': 'Clientes',
    'customerprofile': 'Perfiles de Cliente',
    'invoice': 'Facturas',
    'invoicedetail': 'Detalle de Facturas',
    'purchase': 'Compras',
    'purchasedetail': 'Detalle de Compras',
    'empleado': 'Empleados',
    'categoria': 'Categorías',
    'departamento': 'Departamentos',
    'cobrofactura': 'Cobros de Facturas',
    'pagocompra': 'Pagos de Compras',
    'group': 'Roles',
    'user': 'Usuarios',
    'permission': 'Permisos',
}

# Traducción de la acción codificada en el codename (view_x, add_x, change_x, delete_x).
ACTION_DISPLAY = {
    'view': 'Ver',
    'add': 'Crear',
    'change': 'Editar',
    'delete': 'Eliminar',
}
ACTION_ORDER = ['view', 'add', 'change', 'delete']


class RolePermissionsView(AdminOnlyMixin, DetailView):
    """
    Panel de Gestión de Roles y Permisos:
    - Sidebar izquierdo: todos los roles (Group) del sistema.
    - Panel derecho: permisos del rol seleccionado, agrupados por app/módulo,
      con un checkbox por cada acción nativa de Django (Ver/Crear/Editar/Eliminar).
    """
    model = Group
    template_name = 'security/role_permissions.html'
    context_object_name = 'role'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['roles'] = Group.objects.all().order_by('name')

        assigned_ids = set(self.object.permissions.values_list('id', flat=True))

        # El módulo "Usuarios y Roles" (permisos de auth: User/Group) es
        # administrativo por naturaleza: solo el rol Administrador debe
        # poder verlo/editarlo aquí. Para cualquier otro rol, ni siquiera
        # se muestra la opción, para evitar que se marque por error.
        allowed_app_labels = dict(APP_LABEL_DISPLAY)
        if self.object.name != 'Administrador':
            allowed_app_labels.pop('auth', None)

        perms = (
            Permission.objects
            .filter(content_type__app_label__in=allowed_app_labels.keys())
            .select_related('content_type')
            .order_by('content_type__app_label', 'content_type__model', 'codename')
        )

        # modules = { 'Nombre del módulo': { 'Nombre del modelo': [ {perm, action, checked}, ... ] } }
        modules = {}
        for p in perms:
            app_label = p.content_type.app_label
            model_key = p.content_type.model
            action = p.codename.split('_')[0]
            if action not in ACTION_DISPLAY:
                continue  # ignora permisos personalizados que no sean los 4 nativos

            module_label = allowed_app_labels.get(app_label, app_label)
            model_label = MODEL_NAME_DISPLAY.get(model_key, model_key.capitalize())

            modules.setdefault(module_label, {}).setdefault(model_label, {})[action] = {
                'perm': p,
                'checked': p.id in assigned_ids,
            }

        # Ordena las acciones dentro de cada modelo según ACTION_ORDER, para
        # que siempre salgan en el mismo orden: Ver, Crear, Editar, Eliminar.
        modules_ordered = {}
        for module_label, models_dict in modules.items():
            modules_ordered[module_label] = {}
            for model_label, actions_dict in models_dict.items():
                ordered_actions = [
                    (ACTION_DISPLAY[a], actions_dict[a])
                    for a in ACTION_ORDER if a in actions_dict
                ]
                modules_ordered[module_label][model_label] = ordered_actions

        ctx['modules'] = modules_ordered
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        selected_ids = request.POST.getlist('permisos')
        self.object.permissions.set(Permission.objects.filter(id__in=selected_ids))
        messages.success(request, f'Permisos del rol "{self.object.name}" actualizados correctamente.')
        return redirect('security:role_permissions', pk=self.object.pk)


# === CAMBIO OBLIGATORIO DE CONTRASEÑA (primer login con clave temporal) ===

class CambiarPasswordView(LoginRequiredMixin, PasswordChangeView):
    """
    Sobreescribe la vista de cambio de contraseña de Django para, al
    guardar exitosamente, apagar el flag must_change_password del perfil.
    Se registra en config/urls.py con name='password_change' ANTES del
    include('django.contrib.auth.urls'), para que esta gane la ruta.
    """
    form_class = CambiarPasswordForm
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('billing:home')

    def form_valid(self, form):
        response = super().form_valid(form)
        perfil, _ = PerfilUsuario.objects.get_or_create(user=self.request.user)
        perfil.must_change_password = False
        perfil.save(update_fields=['must_change_password'])
        messages.success(self.request, 'Contraseña actualizada correctamente.')
        return response
