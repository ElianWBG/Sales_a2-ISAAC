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
    'creditos_ventas': 'Créditos de Ventas',
    'creditos_compras': 'Créditos de Compras',
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
    'cuotaventa': 'Cuotas de Venta',
    'pagocuotaventa': 'Pagos de Cuotas de Venta',
    'cuotacompra': 'Cuotas de Compra',
    'pagocuotacompra': 'Pagos de Cuotas de Compra',
    'empleado': 'Empleados',
    'categoria': 'Categorías',
    'departamento': 'Departamentos',
    'cobrofactura': 'Cobros de Facturas',
    'pagocompra': 'Pagos de Compras',
    'group': 'Roles',
    'user': 'Usuarios',
    'permission': 'Permisos',
}

# Traducción de la acción codificada en el codename (view_x, add_x, change_x,
# delete_x, los custom exportar_pdf_x / exportar_excel_x, o los de codename
# fijo como view_purchase_report / imprimir_x).
ACTION_DISPLAY = {
    'view': 'Ver',
    'add': 'Crear',
    'change': 'Editar',
    'delete': 'Eliminar',
    'exportar_pdf': 'PDF',
    'exportar_excel': 'Excel',
    'view_purchase_report': 'Reporte',
    'imprimir': 'Imprimir',
}
ACTION_ORDER = [
    'view', 'add', 'change', 'delete', 'exportar_pdf', 'exportar_excel',
    'view_purchase_report', 'imprimir',
]

# Prefijos de acción de más de un token (a diferencia de view_x/add_x/etc.,
# que son un solo token antes del primer "_"). Se listan del más largo al
# más corto para que exportar_excel_x no se confunda con exportar_pdf_x.
_COMPOUND_ACTION_PREFIXES = ('exportar_excel_', 'exportar_pdf_')

# Permisos custom cuyo codename COMPLETO ya identifica la acción -- a
# diferencia de exportar_pdf_x/exportar_excel_x (un prefijo reutilizado
# por 7 modelos distintos), estos son codenames fijos que además no
# siguen el patrón "acción_modelo":
#   - view_purchase_report: si se partiera por "_" dando el primer
#     token, "view" chocaría con el view_purchase nativo del mismo
#     modelo Purchase y uno pisaría al otro.
#   - imprimir_factura / imprimir_orden_compra / imprimir_plan_pagos
#     (este último repetido en CuotaVenta y CuotaCompra, dos modelos
#     distintos -- no chocan entre sí porque Permission es único por
#     (content_type, codename), no solo por codename): documentado acá
#     igual, aunque el primer token "imprimir" no colisiona hoy con
#     ningún otro ACTION_DISPLAY existente, para que quede explícito y
#     no dependa de que la coincidencia siga siendo casual a futuro.
_EXACT_CODENAME_ACTIONS = {
    'view_purchase_report': 'view_purchase_report',
    'imprimir_factura': 'imprimir',
    'imprimir_orden_compra': 'imprimir',
    'imprimir_plan_pagos': 'imprimir',
}


def _parse_action(codename):
    """
    Extrae la acción de un codename de permiso. Los 4 nativos de Django
    son un solo token (view_brand -> 'view'); los de exportación son dos
    tokens (exportar_pdf_brand -> 'exportar_pdf', no solo 'exportar');
    los de _EXACT_CODENAME_ACTIONS se devuelven tal cual, sin partir.
    """
    if codename in _EXACT_CODENAME_ACTIONS:
        return _EXACT_CODENAME_ACTIONS[codename]
    for prefix in _COMPOUND_ACTION_PREFIXES:
        if codename.startswith(prefix):
            return prefix[:-1]  # quita el "_" final
    return codename.split('_')[0]

# Modelos "hijo" que solo se crean/editan junto a su registro padre (Factura,
# Cliente, Compra) y nunca por separado: sus 4 permisos view/add/change/delete
# no están conectados a ninguna vista propia (confirmado empíricamente), así
# que mostrarlos en la matriz de Roles→Permisos prometía un control que en
# realidad no existe -- si el rol puede crear/editar el padre, ya puede
# crear/editar sus líneas/perfil, sin necesidad de un permiso aparte. Se
# excluyen solo de esta pantalla; los permisos siguen intactos en la BD
# (Django los regenera de todos modos si se los borra y se corre migrate).
#   - invoicedetail/customerprofile/purchasedetail: líneas de factura/compra
#     y perfil de cliente, siempre junto a su padre.
#   - configuracionsistema: registro singleton (ConfiguracionUpdateView),
#     protegido solo por AdminOnlyMixin (grupo Administrador), nunca por
#     ninguno de los 4 permisos nativos -- ni siquiera "Editar", la única
#     acción que existe de verdad para este modelo.
#   - perfilusuario: se crea por ORM directo dentro de UserCreateView /
#     CambiarPasswordView, sin ninguna vista ni permission_required propio.
MODELS_EXCLUDED_FROM_MATRIX = {
    'invoicedetail', 'customerprofile', 'purchasedetail',
    'configuracionsistema', 'perfilusuario',
}

# Modelos donde SOLO una parte de las 4 acciones nativas está conectada a
# una vista real -- a diferencia de MODELS_EXCLUDED_FROM_MATRIX (modelo
# completo decorativo), acá se oculta únicamente la(s) acción(es) sin
# efecto, fila por fila:
#   - CuotaVenta/CuotaCompra: se generan solo automáticamente dentro de
#     invoice_create/purchase_create (generar_cuotas), nunca por un
#     formulario propio -> add/change no hacen nada. view (CuotaListView)
#     y delete (CuotaDeleteView) sí son reales.
#   - PagoCuotaVenta/PagoCuotaCompra: no existe vista para editar ni
#     eliminar un pago ya registrado -> change/delete no hacen nada.
#     view (historial) y add (registrar_pago/pago en lote) sí son reales.
ACTIONS_EXCLUDED_PER_MODEL = {
    'cuotaventa': {'add', 'change'},
    'cuotacompra': {'add', 'change'},
    'pagocuotaventa': {'change', 'delete'},
    'pagocuotacompra': {'change', 'delete'},
}


def _permiso_visible_en_matriz(model_key, action):
    """
    True si el checkbox de (model_key, action) se renderiza como editable
    en la matriz de Roles→Permisos -- única fuente de verdad para esta
    exclusión, usada tanto al construir la matriz (get_context_data) como
    al guardarla (post). Que ambas consulten la misma función evita que
    se desincronicen si alguna vez se agrega/quita una exclusión.
    """
    if model_key in MODELS_EXCLUDED_FROM_MATRIX:
        return False
    if action in ACTIONS_EXCLUDED_PER_MODEL.get(model_key, ()):
        return False
    return True


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
            action = _parse_action(p.codename)
            if action not in ACTION_DISPLAY:
                continue  # ignora permisos personalizados que no sean los 4 nativos
            if not _permiso_visible_en_matriz(model_key, action):
                continue

            module_label = allowed_app_labels.get(app_label, app_label)
            model_label = MODEL_NAME_DISPLAY.get(model_key, model_key.capitalize())

            modules.setdefault(module_label, {}).setdefault(model_label, {})[action] = {
                'perm': p,
                'checked': p.id in assigned_ids,
            }

        # Ordena las acciones dentro de cada modelo según ACTION_ORDER, para
        # que siempre salgan en el mismo orden: Ver, Crear, Editar, Eliminar,
        # PDF, Excel. Siempre se emiten las 6 columnas (con info=None en la
        # que no aplica -- ej. PDF/Excel en un modelo sin ExportMixin, o
        # Crear/Editar en CuotaVenta): el <thead> de la tabla tiene 6
        # posiciones fijas, así que si una fila renderizara menos <td> se
        # correrían a la izquierda y quedarían debajo del header equivocado.
        # El template solo dibuja el checkbox cuando info no es None; la
        # celda igual se emite (vacía) para mantener la alineación.
        modules_ordered = {}
        for module_label, models_dict in modules.items():
            modules_ordered[module_label] = {}
            for model_label, actions_dict in models_dict.items():
                ordered_actions = [
                    (ACTION_DISPLAY[a], actions_dict.get(a))
                    for a in ACTION_ORDER
                ]
                modules_ordered[module_label][model_label] = ordered_actions

        ctx['modules'] = modules_ordered
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        selected_ids = {int(i) for i in request.POST.getlist('permisos') if i.isdigit()}

        # BUG REAL encontrado y corregido: la matriz no muestra TODOS los
        # permisos del sistema (ver MODELS_EXCLUDED_FROM_MATRIX /
        # ACTIONS_EXCLUDED_PER_MODEL) -- los ocultos nunca tienen checkbox
        # en el HTML, así que nunca llegan en el POST. Antes, `.set()`
        # reemplazaba el set COMPLETO con lo recibido, así que guardar la
        # matriz de un rol que ya tuviera alguno de esos permisos asignados
        # (ej. Vendedor con view_customerprofile) lo borraba en silencio,
        # aunque el usuario no hubiera tocado nada relacionado. Ahora se
        # preservan tal cual estaban los permisos ocultos que el rol ya
        # tenía, y solo se reemplazan los que sí son editables en pantalla.
        permisos_ocultos_asignados = [
            p for p in self.object.permissions.select_related('content_type')
            if not _permiso_visible_en_matriz(p.content_type.model, _parse_action(p.codename))
        ]
        nuevos_editables = Permission.objects.filter(id__in=selected_ids)
        self.object.permissions.set(list(nuevos_editables) + permisos_ocultos_asignados)

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
