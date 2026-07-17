import re
import secrets
import string

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View

from shared.mixins import GroupRequiredMixin
from shared.emails import send_welcome_email_with_temp_password
from .forms import CambiarPasswordForm, UserUpdateForm, GroupForm, PermissionForm, AdminUserCreateForm
from .models import PerfilUsuario, RoleDefaultPermissions
from .utils import generar_username, es_ultimo_administrador_activo
from .management.commands.setup_roles import ROLES, resolve_role_permissions

# Los 6 roles que setup_roles.py define como fuente de verdad en código --
# cualquier otro Group es "custom" (creado a mano con "+ Nuevo rol"). Ver
# RoleDefaultPermissionsSaveView/ApplyView y RolePermissionsView.
FIXED_ROLE_NAMES = set(ROLES.keys())


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

        enviado = send_welcome_email_with_temp_password(user, temp_password, request=self.request)

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

    def form_valid(self, form):
        # self.object ya fue mutado en memoria por el _post_clean() del
        # ModelForm (is_active, etc. ya reflejan el valor NUEVO aunque
        # todavía no se guardó en la BD) -- se necesita una lectura fresca
        # para comparar el estado ANTES de esta edición.
        original = User.objects.get(pk=self.object.pk)
        if original.groups.filter(name='Administrador').exists():
            cambia_de_rol = form.cleaned_data['role'].name != 'Administrador'
            se_desactiva = not form.cleaned_data['is_active']
            if (cambia_de_rol or se_desactiva) and es_ultimo_administrador_activo(original):
                messages.error(
                    self.request,
                    'No puedes quitarle el rol de Administrador ni desactivar '
                    'al único Administrador activo del sistema.'
                )
                return redirect('security:user_update', pk=original.pk)
        return super().form_valid(form)


class UserDeleteView(AdminOnlyMixin, DeleteView):
    model = User
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:user_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.groups.filter(name='Administrador').exists() and es_ultimo_administrador_activo(self.object):
            messages.error(request, 'No puedes eliminar al único Administrador activo del sistema.')
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)


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

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.name == 'Administrador':
            messages.error(
                request,
                'No puedes eliminar el rol "Administrador": el sistema siempre '
                'debe tener este rol disponible, sin importar cuántos usuarios tenga.'
            )
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)


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
    'cancelar_invoice_paypal': 'Cancelar PayPal',
}
ACTION_ORDER = [
    'view', 'add', 'change', 'delete', 'exportar_pdf', 'exportar_excel',
    'view_purchase_report', 'imprimir', 'cancelar_invoice_paypal',
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
#   - cancelar_invoice_paypal: único en Invoice, sin default asignado a
#     ningún rol (acción nueva, no un fix de algo que ya existía).
_EXACT_CODENAME_ACTIONS = {
    'view_purchase_report': 'view_purchase_report',
    'imprimir_factura': 'imprimir',
    'imprimir_orden_compra': 'imprimir',
    'imprimir_plan_pagos': 'imprimir',
    'cancelar_invoice_paypal': 'cancelar_invoice_paypal',
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
#     formulario propio -> add/change no hacen nada. CuotaDeleteView
#     existe y funciona, pero no hay ningún botón/link en toda la UI que
#     apunte a esa URL (confirmado: cero referencias a "cuota_delete" en
#     los templates) -- solo alcanzable escribiendo la URL a mano, así
#     que delete tampoco tiene efecto real desde la interfaz. Únicamente
#     view (CuotaListView/CuotaPendientesListView) es real.
#   - PagoCuotaVenta/PagoCuotaCompra: no existe vista para editar ni
#     eliminar un pago ya registrado -> change/delete no hacen nada.
#     view (historial) y add (registrar_pago/pago en lote) sí son reales.
ACTIONS_EXCLUDED_PER_MODEL = {
    'cuotaventa': {'add', 'change', 'delete'},
    'cuotacompra': {'add', 'change', 'delete'},
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

    Ojo: esto solo cubre exclusiones DENTRO de una app que la matriz ya
    trackea -- ver _permiso_editable_en_matriz para la app_label completa.
    """
    if model_key in MODELS_EXCLUDED_FROM_MATRIX:
        return False
    if action in ACTIONS_EXCLUDED_PER_MODEL.get(model_key, ()):
        return False
    return True


def _allowed_app_labels(role):
    """
    App labels que la matriz de Roles→Permisos muestra para `role` --
    extraído acá para que get_context_data() (qué se muestra) y post()
    (qué se preserva al guardar) usen siempre la misma fuente. 'auth'
    (User/Group/Permission) solo se muestra si el rol es Administrador.
    """
    allowed = dict(APP_LABEL_DISPLAY)
    if role.name != 'Administrador':
        allowed.pop('auth', None)
    return allowed


def _permiso_editable_en_matriz(role, permission):
    """
    True si `permission` tiene un checkbox editable en la matriz de
    Roles→Permisos PARA ESTE ROL -- única fuente de verdad usada tanto al
    construir la matriz como al guardarla (post()).

    BUG REAL encontrado y corregido acá: _permiso_visible_en_matriz por sí
    sola solo mira modelo/acción DENTRO de una app ya trackeada -- nunca
    contempla permisos de apps que ni siquiera están en APP_LABEL_DISPLAY
    (los nativos de Django: contenttypes, sessions, admin.logentry) ni
    'auth' para un rol que no sea Administrador. Como esos permisos jamás
    tienen checkbox en ningún módulo, post() los trataba como "visibles"
    (nunca entraban a permisos_ocultos_asignados) y .set() los borraba en
    CUALQUIER guardado de CUALQUIER rol que los tuviera -- por ejemplo
    Administrador, que los recibe vía setup_roles.py ('__all__'). Con este
    chequeo de app_label agregado, quedan preservados sin importar qué rol
    se guarde ni cuántas veces.
    """
    if permission.content_type.app_label not in _allowed_app_labels(role):
        return False
    return _permiso_visible_en_matriz(permission.content_type.model, _parse_action(permission.codename))


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

        # Botones "Guardar como predeterminado" / "Permisos predeterminados"
        # -- ver RoleDefaultPermissionsSaveView/ApplyView. Fijo = setup_roles.py
        # es la fuente de verdad, no se guarda un default aparte. Custom =
        # "Guardar" siempre visible; "Permisos predeterminados" solo si ya
        # hay uno guardado.
        ctx['es_rol_fijo'] = self.object.name in FIXED_ROLE_NAMES
        ctx['default_guardado_existe'] = (
            not ctx['es_rol_fijo']
            and RoleDefaultPermissions.objects.filter(group=self.object).exists()
        )

        assigned_ids = set(self.object.permissions.values_list('id', flat=True))

        # El módulo "Usuarios y Roles" (permisos de auth: User/Group) es
        # administrativo por naturaleza: solo el rol Administrador debe
        # poder verlo/editarlo aquí. Para cualquier otro rol, ni siquiera
        # se muestra la opción, para evitar que se marque por error.
        allowed_app_labels = _allowed_app_labels(self.object)

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
        # ACTIONS_EXCLUDED_PER_MODEL, y _allowed_app_labels para apps
        # enteras fuera de la matriz como contenttypes/sessions/admin) --
        # los ocultos nunca tienen checkbox en el HTML, así que nunca
        # llegan en el POST. Antes, `.set()` reemplazaba el set COMPLETO
        # con lo recibido, así que guardar la matriz de un rol que ya
        # tuviera alguno de esos permisos asignados (ej. Vendedor con
        # view_customerprofile, o Administrador con contenttypes/sessions
        # vía setup_roles.py) lo borraba en silencio, aunque el usuario no
        # hubiera tocado nada relacionado. Ahora se preservan tal cual
        # estaban los permisos ocultos que el rol ya tenía, y solo se
        # reemplazan los que sí son editables en pantalla.
        permisos_ocultos_asignados = [
            p for p in self.object.permissions.select_related('content_type')
            if not _permiso_editable_en_matriz(self.object, p)
        ]
        nuevos_editables = Permission.objects.filter(id__in=selected_ids)
        self.object.permissions.set(list(nuevos_editables) + permisos_ocultos_asignados)

        messages.success(request, f'Permisos del rol "{self.object.name}" actualizados correctamente.')

        # Vuelve a la sección del acordeón que el usuario tenía abierta al
        # guardar (ver JS de role_permissions.html), en vez de siempre a la
        # primera. Es puramente de UX -- el id ("modN") se valida estricto
        # antes de pegarlo en la URL de redirect, nunca se usa en la lógica
        # de guardado de arriba.
        seccion_abierta = request.POST.get('seccion_abierta', '')
        url = reverse('security:role_permissions', kwargs={'pk': self.object.pk})
        if re.fullmatch(r'mod\d+', seccion_abierta):
            url = f'{url}#{seccion_abierta}'
        return redirect(url)


class RoleDefaultPermissionsSaveView(AdminOnlyMixin, View):
    """
    Botón "Guardar como predeterminado" -- solo para roles CUSTOM (fuera
    de FIXED_ROLE_NAMES). Guarda una fotografía COMPLETA de los permisos
    actuales del rol (todos, no solo los visibles en la matriz) en
    RoleDefaultPermissions. La confirmación de "¿sobrescribir?" la hace el
    template (modal Bootstrap #modalGuardarDefault) usando
    default_guardado_existe -- acá solo se re-verifica server-side que el
    rol no sea uno de los 6 fijos, por si alguien arma el POST a mano.
    """
    def post(self, request, pk):
        role = get_object_or_404(Group, pk=pk)
        if role.name in FIXED_ROLE_NAMES:
            messages.error(
                request,
                f'"{role.name}" es un rol del sistema -- su fuente de verdad es '
                f'setup_roles.py, no admite guardar un default aparte.'
            )
            return redirect('security:role_permissions', pk=role.pk)

        default_obj, created = RoleDefaultPermissions.objects.get_or_create(group=role)
        # set() acá es la fotografía completa, no el merge parcial de
        # RolePermissionsView.post() -- se guarda TODO lo que el rol tiene
        # ahora mismo (visible u oculto en la matriz), sin filtrar nada.
        default_obj.permissions.set(role.permissions.all())

        # extra_tags='auto-dismiss': SOLO estos 2 mensajes de éxito llevan
        # este flag (ver base.html) -- el resto de los messages.success/
        # error del sistema no lo usan y siguen cerrándose solo con la X.
        if created:
            messages.success(request, f'Permisos predeterminados guardados para "{role.name}".', extra_tags='auto-dismiss')
        else:
            messages.success(request, f'Permisos predeterminados de "{role.name}" actualizados.', extra_tags='auto-dismiss')
        return redirect('security:role_permissions', pk=role.pk)


class RoleDefaultPermissionsApplyView(AdminOnlyMixin, View):
    """
    Botón "Permisos predeterminados" -- reemplaza los permisos ACTUALES
    del rol por su default:
      - Rol fijo: resuelve ROLES[nombre] de setup_roles.py con
        resolve_role_permissions() y lo aplica SOLO a este rol (no corre
        el comando completo, no toca los otros 5).
      - Rol custom: aplica la fotografía guardada en RoleDefaultPermissions.
        Si todavía no guardó ninguna, no hay nada que aplicar (el botón ni
        se muestra en ese caso, pero se re-valida server-side igual).

    En los dos casos es un .set() directo y completo (mismo patrón ya
    probado en el fix del bug de conteo) -- no pasa por el merge parcial
    de permisos_ocultos_asignados porque acá no hace falta: el conjunto a
    aplicar ya es completo por construcción (todo el default), no un
    subconjunto editable de la matriz.
    """
    def post(self, request, pk):
        role = get_object_or_404(Group, pk=pk)

        if role.name in FIXED_ROLE_NAMES:
            perms = resolve_role_permissions(ROLES[role.name])
            role.permissions.set(perms)
            messages.success(
                request,
                f'Se restauraron los permisos predeterminados de "{role.name}" (setup_roles.py).',
                extra_tags='auto-dismiss',
            )
        else:
            try:
                default_obj = role.default_permissions
            except RoleDefaultPermissions.DoesNotExist:
                messages.error(
                    request,
                    f'"{role.name}" todavía no tiene permisos predeterminados guardados.'
                )
                return redirect('security:role_permissions', pk=role.pk)
            role.permissions.set(default_obj.permissions.all())
            messages.success(
                request,
                f'Se restauraron los permisos predeterminados guardados de "{role.name}".',
                extra_tags='auto-dismiss',
            )
        return redirect('security:role_permissions', pk=role.pk)


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
