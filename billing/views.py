import json
import logging
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from .mixins import ExportMixin
from .models import *
from django.db.models import Q
from django.db.models import F
from django.db import transaction
from .forms import (
    BrandForm, ProductGroupForm, SupplierForm,
    ProductForm, CustomerForm, InvoiceForm, InvoiceDetailFormSet,
    ProductSearchForm, BrandSearchForm, ProductGroupSearchForm,
    SupplierSearchForm, CustomerSearchForm, InvoiceSearchForm,
    ConfiguracionForm,
)

from decimal import Decimal
from shared.mixins import (
    StaffRequiredMixin, ProtectedDeleteMixin, PermissionRequiredMixin,
    SuccessUrlPreservePageMixin, redirect_preserving_page, GracefulPaginationMixin,
    AnyCrudPermissionRequiredMixin,
)
from shared.decorators import audit_action, permission_required_with_message, any_crud_permission_required
from shared.emails import send_invoice_email
from shared.paypal_client import create_paypal_order, capture_paypal_order, extract_capture_data, PayPalError
from security.views import AdminOnlyMixin
from .invoice_pdf import generar_pdf_factura
from django.db.models import ProtectedError
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

# === HOME (Página principal) ===
@login_required
def home(request):
    """Vista principal del sistema. Muestra resumen general."""
    context = {
        'total_brands': Brand.objects.count(),
        'total_products': Product.objects.count(),
        'total_customers': Customer.objects.count(),
        'total_invoices': Invoice.objects.count(),
        'recent_invoices': Invoice.objects.all()[:5],  # Últimas 5
        'low_stock': Product.objects.filter(stock__lte=5, is_active=True),
    }
    return render(request, 'billing/home.html', context)


# ── Definición de columnas disponibles para Productos ────────────────────────
PRODUCT_ALL_COLUMNS = [
    {
        'key':     'image',
        'label':   'Imagen',
        'default': True,
        'export':  (lambda obj: 'Con imagen' if obj.image else 'Sin imagen', 'Imagen'),
    },
    {
        'key':     'name',
        'label':   'Nombre',
        'default': True,
        'export':  ('name', 'Nombre'),
    },
    {
        'key':     'brand',
        'label':   'Marca',
        'default': True,
        'export':  ('brand.name', 'Marca'),
    },
    {
        'key':     'group',
        'label':   'Categoría',
        'default': True,
        'export':  ('group.name', 'Categoría'),
    },
    {
        'key':     'unit_price',
        'label':   'Precio',
        'default': True,
        'export':  ('unit_price', 'Precio ($)'),
    },
    {
        'key':     'stock',
        'label':   'Stock',
        'default': True,
        'export':  ('stock', 'Stock'),
    },
    {
        'key':     'balance',
        'label':   'Balance',
        'default': True,
        'export':  (lambda obj: str(obj.balance), 'Balance ($)'),
    },
    {
        'key':     'suppliers',
        'label':   'Proveedores',
        'default': True,
        'export':  (lambda obj: ', '.join(s.name for s in obj.suppliers.all()), 'Proveedores'),
    },
    {
        'key':     'id',
        'label':   'Código (ID)',
        'default': False,
        'export':  ('id', 'Código'),
    },
    {
        'key':     'description',
        'label':   'Descripción',
        'default': False,
        'export':  ('description', 'Descripción'),
    },
    {
        'key':     'is_active',
        'label':   'Estado',
        'default': False,
        'export':  (lambda obj: 'Sí' if obj.is_active else 'No', 'Estado'),
    },
    {
        'key':     'created_at',
        'label':   'Fecha creación',
        'default': False,
        'export':  (lambda obj: obj.created_at.strftime('%d/%m/%Y'), 'Fecha creación'),
    },
]

# ── Definición de columnas disponibles para Marcas ────────────────────────
BRAND_ALL_COLUMNS = [
    {
        'key':     'name',
        'label':   'Nombre',
        'default': True,
        'export':  ('name', 'Nombre'),
    },
    {
        'key':     'description',
        'label':   'Descripción',
        'default': True,
        'export':  ('description', 'Descripción'),
    },
    {
        'key':     'is_active',
        'label':   'Estado',
        'default': True,
        'export':  (lambda obj: 'Sí' if obj.is_active else 'No', 'Estado'),
    },
    {
        'key':     'created_at',
        'label':   'Fecha creación',
        'default': False,
        'export':  (lambda obj: obj.created_at.strftime('%d/%m/%Y'), 'Fecha creación'),
    },
]

# ── Definición de columnas disponibles para Grupos de Productos ────────────────────────
PRODUCTGROUP_ALL_COLUMNS = [
    {
        'key':     'name',
        'label':   'Nombre',
        'default': True,
        'export':  ('name', 'Nombre'),
    },
    {
        'key':     'is_active',
        'label':   'Estado',
        'default': True,
        'export':  (lambda obj: 'Sí' if obj.is_active else 'No', 'Estado'),
    },
    {
        'key':     'created_at',
        'label':   'Fecha creación',
        'default': False,
        'export':  (lambda obj: obj.created_at.strftime('%d/%m/%Y'), 'Fecha creación'),
    },
]

# ── Definición de columnas disponibles para Proveedores ────────────────────────
SUPPLIER_ALL_COLUMNS = [
    {
        'key':     'name',
        'label':   'Nombre',
        'default': True,
        'export':  ('name', 'Nombre'),
    },
    {
        'key':     'contact_name',
        'label':   'Contacto',
        'default': True,
        'export':  ('contact_name', 'Contacto'),
    },
    {
        'key':     'email',
        'label':   'Email',
        'default': True,
        'export':  ('email', 'Email'),
    },
    {
        'key':     'phone',
        'label':   'Teléfono',
        'default': True,
        'export':  ('phone', 'Teléfono'),
    },
    {
        'key':     'address',
        'label':   'Dirección',
        'default': False,
        'export':  ('address', 'Dirección'),
    },
    {
        'key':     'is_active',
        'label':   'Estado',
        'default': False,
        'export':  (lambda obj: 'Sí' if obj.is_active else 'No', 'Estado'),
    },
]

# ── Definición de columnas disponibles para Clientes ────────────────────────
CUSTOMER_ALL_COLUMNS = [
    {
        'key':     'dni',
        'label':   'DNI/RUC',
        'default': True,
        'export':  ('dni', 'DNI/RUC'),
    },
    {
        'key':     'last_name',
        'label':   'Apellido',
        'default': True,
        'export':  ('last_name', 'Apellido'),
    },
    {
        'key':     'first_name',
        'label':   'Nombre',
        'default': True,
        'export':  ('first_name', 'Nombre'),
    },
    {
        'key':     'email',
        'label':   'Email',
        'default': True,
        'export':  ('email', 'Email'),
    },
    {
        'key':     'phone',
        'label':   'Teléfono',
        'default': True,
        'export':  ('phone', 'Teléfono'),
    },
    {
        'key':     'address',
        'label':   'Dirección',
        'default': False,
        'export':  ('address', 'Dirección'),
    },
    {
        'key':     'is_active',
        'label':   'Estado',
        'default': False,
        'export':  (lambda obj: 'Sí' if obj.is_active else 'No', 'Estado'),
    },
]

# ── Definición de columnas disponibles para Facturas ────────────────────────
INVOICE_ALL_COLUMNS = [
    {
        'key':     'id',
        'label':   'N° Factura',
        'default': True,
        'export':  ('id', 'N° Factura'),
    },
    {
        'key':     'customer',
        'label':   'Cliente',
        'default': True,
        'export':  (lambda obj: obj.customer.full_name, 'Cliente'),
    },
    {
        'key':     'invoice_date',
        'label':   'Fecha',
        'default': True,
        'export':  (lambda obj: obj.invoice_date.strftime('%d/%m/%Y %H:%M'), 'Fecha'),
    },
    {
        'key':     'subtotal',
        'label':   'Subtotal',
        'default': True,
        'export':  ('subtotal', 'Subtotal ($)'),
    },
    {
        'key':     'tax',
        'label':   'IVA',
        'default': True,
        'export':  ('tax', 'IVA ($)'),
    },
    {
        'key':     'total',
        'label':   'Total',
        'default': True,
        'export':  ('total', 'Total ($)'),
    },
]

# === BRAND (CBV) ===
class BrandListView(GracefulPaginationMixin, ExportMixin, LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    model = Brand
    template_name = 'billing/brand_list.html'
    context_object_name = 'items'
    paginate_by = 3
    export_filename = 'marcas'
    ALL_COLUMNS = BRAND_ALL_COLUMNS

    def get_active_col_keys(self):
        cols_param = self.request.GET.get('cols', '').strip()
        if cols_param:
            all_keys = {c['key'] for c in self.ALL_COLUMNS}
            valid = [k.strip() for k in cols_param.split(',') if k.strip() in all_keys]
            if valid:
                return valid
        return [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]

    def get_dynamic_export_fields(self):
        active = set(self.get_active_col_keys())
        return [
            col['export']
            for col in self.ALL_COLUMNS
            if col['key'] in active and col.get('export') is not None
        ]

    @property
    def export_fields(self):
        return self.get_dynamic_export_fields()

    def get_queryset(self):
        qs = Brand.objects.all()
        form = BrandSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('name'):
                qs = qs.filter(name__icontains=form.cleaned_data['name'])
            val = form.cleaned_data.get('is_active')
            if val in ('0', '1'):
                qs = qs.filter(is_active=(val == '1'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_form'] = BrandSearchForm(self.request.GET)
        ctx['all_columns'] = self.ALL_COLUMNS
        ctx['all_col_keys_json'] = json.dumps([c['key'] for c in self.ALL_COLUMNS])
        ctx['default_col_keys_json'] = json.dumps(
            [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]
        )
        return ctx

@login_required
@permission_required_with_message('billing.add_brand', redirect_url='/brands/')
@audit_action('CREATE_BRAND')
def brand_create(request):
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Marca Creada exitosamente!')
            return redirect('billing:brand_list')
    else: form = BrandForm()
    return render(request, 'billing/brand_form.html', {'form':form, 'title':'Crear Marca'})

@login_required
@permission_required_with_message('billing.change_brand', redirect_url='/brands/')
@audit_action('UPDATE_BRAND')
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            form.save()
            messages.success(request, 'Marca actulizada exitosamente!')
            return redirect('billing:brand_list')
    else: form = BrandForm(instance=brand)
    return render(request, 'billing/brand_form.html', {'form':form, 'title':'Editar Marca'})

@login_required
@permission_required_with_message('billing.delete_brand', redirect_url='/brands/')
@audit_action('DELETE_BRAND')
def brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        try:
            brand.delete()
            messages.success(request, 'Marca eliminada exitosamente!')
        except ProtectedError:
            messages.error(
                request,
                f'No se puede eliminar "{brand.name}" porque tiene productos asociados.'
            )
        return redirect_preserving_page(request, 'billing:brand_list')
    return render(request, 'billing/brand_confirm_delete.html', {'object': brand})

class BrandDetailView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, DetailView):
    model = Brand
    template_name = 'billing/brand_detail.html'
    context_object_name = 'brand'

# === PRODUCTGROUP (CBV) ===
class ProductGroupListView(GracefulPaginationMixin, ExportMixin, LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    model = ProductGroup
    template_name = 'billing/product_group_list.html'
    context_object_name = 'items'
    paginate_by = 3
    export_filename = 'grupos'
    ALL_COLUMNS = PRODUCTGROUP_ALL_COLUMNS

    def get_active_col_keys(self):
        cols_param = self.request.GET.get('cols', '').strip()
        if cols_param:
            all_keys = {c['key'] for c in self.ALL_COLUMNS}
            valid = [k.strip() for k in cols_param.split(',') if k.strip() in all_keys]
            if valid:
                return valid
        return [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]

    def get_dynamic_export_fields(self):
        active = set(self.get_active_col_keys())
        return [
            col['export']
            for col in self.ALL_COLUMNS
            if col['key'] in active and col.get('export') is not None
        ]

    @property
    def export_fields(self):
        return self.get_dynamic_export_fields()

    def get_queryset(self):
        qs = ProductGroup.objects.all()
        form = ProductGroupSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('name'):
                qs = qs.filter(name__icontains=form.cleaned_data['name'])
            val = form.cleaned_data.get('is_active')
            if val in ('0', '1'):
                qs = qs.filter(is_active=(val == '1'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_form'] = ProductGroupSearchForm(self.request.GET)
        ctx['all_columns'] = self.ALL_COLUMNS
        ctx['all_col_keys_json'] = json.dumps([c['key'] for c in self.ALL_COLUMNS])
        ctx['default_col_keys_json'] = json.dumps(
            [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]
        )
        return ctx

class ProductGroupCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ProductGroup;
    form_class = ProductGroupForm;
    template_name = 'billing/product_group_form.html';
    success_url = reverse_lazy('billing:productgroup_list')
    permission_required = 'billing.add_productgroup'
    permission_redirect_url = '/groups/'

class ProductGroupUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ProductGroup;
    form_class = ProductGroupForm;
    template_name = 'billing/product_group_form.html';
    success_url = reverse_lazy('billing:productgroup_list')
    permission_required = 'billing.change_productgroup'
    permission_redirect_url = '/groups/'

class ProductGroupDeleteView(SuccessUrlPreservePageMixin, ProtectedDeleteMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ProductGroup
    template_name = 'billing/product_group_confirm_delete.html'
    success_url = reverse_lazy('billing:productgroup_list')
    protected_message = 'No se puede eliminar el grupo porque tiene productos asociados.'
    permission_required = 'billing.delete_productgroup'
    permission_redirect_url = '/groups/'

class ProductGroupDetailView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, DetailView):
    model = ProductGroup
    template_name = 'billing/product_group_detail.html'
    context_object_name = 'productgroup'

# === SUPPLIER (CBV) ===
class SupplierListView(GracefulPaginationMixin, ExportMixin, LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    model = Supplier
    template_name = 'billing/supplier_list.html'
    context_object_name = 'items'
    paginate_by = 3
    export_filename = 'proveedores'
    ALL_COLUMNS = SUPPLIER_ALL_COLUMNS

    def get_active_col_keys(self):
        cols_param = self.request.GET.get('cols', '').strip()
        if cols_param:
            all_keys = {c['key'] for c in self.ALL_COLUMNS}
            valid = [k.strip() for k in cols_param.split(',') if k.strip() in all_keys]
            if valid:
                return valid
        return [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]

    def get_dynamic_export_fields(self):
        active = set(self.get_active_col_keys())
        return [
            col['export']
            for col in self.ALL_COLUMNS
            if col['key'] in active and col.get('export') is not None
        ]

    @property
    def export_fields(self):
        return self.get_dynamic_export_fields()

    def get_queryset(self):
        qs = Supplier.objects.all()
        form = SupplierSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('name'):
                qs = qs.filter(name__icontains=form.cleaned_data['name'])
            if form.cleaned_data.get('contact_name'):
                qs = qs.filter(contact_name__icontains=form.cleaned_data['contact_name'])
            if form.cleaned_data.get('email'):
                qs = qs.filter(email__icontains=form.cleaned_data['email'])
            if form.cleaned_data.get('phone'):
                qs = qs.filter(phone__icontains=form.cleaned_data['phone'])
            val = form.cleaned_data.get('is_active')
            if val in ('0', '1'):
                qs = qs.filter(is_active=(val == '1'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_form'] = SupplierSearchForm(self.request.GET)
        ctx['all_columns'] = self.ALL_COLUMNS
        ctx['all_col_keys_json'] = json.dumps([c['key'] for c in self.ALL_COLUMNS])
        ctx['default_col_keys_json'] = json.dumps(
            [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]
        )
        return ctx

class SupplierCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Supplier; form_class = SupplierForm;
    template_name = 'billing/supplier_form.html';
    success_url = reverse_lazy('billing:supplier_list')
    permission_required = 'billing.add_supplier'
    permission_redirect_url = '/suppliers/'
class SupplierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Supplier;
    form_class = SupplierForm;
    template_name = 'billing/supplier_form.html';
    success_url = reverse_lazy('billing:supplier_list')
    permission_required = 'billing.change_supplier'
    permission_redirect_url = '/suppliers/'
class SupplierDeleteView(SuccessUrlPreservePageMixin, ProtectedDeleteMixin, LoginRequiredMixin, StaffRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Supplier
    template_name = 'billing/supplier_confirm_delete.html'
    success_url = reverse_lazy('billing:supplier_list')
    staff_redirect_url = '/suppliers/'
    protected_message = 'No se puede eliminar el proveedor porque tiene productos asociados.'
    permission_required = 'billing.delete_supplier'
    permission_redirect_url = '/suppliers/'
class SupplierDetailView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, DetailView):
    model = Supplier
    template_name = 'billing/supplier_detail.html'
    context_object_name = 'supplier'

# === PRODUCT (CBV) ===
class ProductListView(GracefulPaginationMixin, ExportMixin, LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    model = Product
    template_name = 'billing/product_list.html'
    context_object_name = 'items'
    paginate_by = 3
    export_filename = 'productos'
    ALL_COLUMNS = PRODUCT_ALL_COLUMNS

    def get_active_col_keys(self):
        cols_param = self.request.GET.get('cols', '').strip()
        if cols_param:
            all_keys = {c['key'] for c in self.ALL_COLUMNS}
            valid = [k.strip() for k in cols_param.split(',') if k.strip() in all_keys]
            if valid:
                return valid
        return [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]

    def get_dynamic_export_fields(self):
        active = set(self.get_active_col_keys())
        return [
            col['export']
            for col in self.ALL_COLUMNS
            if col['key'] in active and col.get('export') is not None
        ]

    def get_queryset(self):
        qs = (
            Product.objects
            .select_related('brand', 'group')
            .prefetch_related('suppliers')
            .order_by('name')
        )
        form = ProductSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('name'):
                qs = qs.filter(name__icontains=form.cleaned_data['name'])
            if form.cleaned_data.get('brand'):
                qs = qs.filter(brand=form.cleaned_data['brand'])
            if form.cleaned_data.get('group'):
                qs = qs.filter(group=form.cleaned_data['group'])
            if form.cleaned_data.get('supplier'):
                qs = qs.filter(suppliers=form.cleaned_data['supplier'])
            if form.cleaned_data.get('price_min') is not None:
                qs = qs.filter(unit_price__gte=form.cleaned_data['price_min'])
            if form.cleaned_data.get('price_max') is not None:
                qs = qs.filter(unit_price__lte=form.cleaned_data['price_max'])
            if form.cleaned_data.get('stock_min') is not None:
                qs = qs.filter(stock__gte=form.cleaned_data['stock_min'])
            if form.cleaned_data.get('stock_max') is not None:
                qs = qs.filter(stock__lte=form.cleaned_data['stock_max'])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_form'] = ProductSearchForm(self.request.GET)
        ctx['all_columns'] = self.ALL_COLUMNS
        ctx['all_col_keys_json'] = json.dumps([c['key'] for c in self.ALL_COLUMNS])
        ctx['default_col_keys_json'] = json.dumps(
            [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]
        )
        return ctx
class ProductCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')
    permission_required = 'billing.add_product'
    permission_redirect_url = '/products/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_edit'] = False
        ctx['page_title'] = 'Nuevo Producto'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f'Producto "{form.instance.name}" creado exitosamente.')
        return super().form_valid(form)

class ProductUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')
    permission_required = 'billing.change_product'
    permission_redirect_url = '/products/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_edit'] = True
        ctx['page_title'] = f'Editar: {self.object.name}'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f'Producto "{form.instance.name}" actualizado exitosamente.')
        return super().form_valid(form)

class ProductDeleteView(SuccessUrlPreservePageMixin, ProtectedDeleteMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Product
    template_name = 'billing/product_confirm_delete.html'
    success_url = reverse_lazy('billing:product_list')
    protected_message = 'No se puede eliminar el producto porque está en una o más facturas.'
    permission_required = 'billing.delete_product'
    permission_redirect_url = '/products/'

class ProductDetailView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, DetailView):
    model = Product;
    template_name = 'billing/product_detail.html';
    context_object_name = 'product'

@login_required
@permission_required_with_message('billing.view_product', redirect_url='/')
def product_price(request, pk):
    """Endpoint JSON de solo lectura: precio actual de un producto (autocompletado en Factura/Compra)."""
    product = get_object_or_404(Product, pk=pk)
    return JsonResponse({'precio': str(product.unit_price)})


@login_required
def customer_create_ajax(request):
    """
    Alta rápida de Cliente desde el modal de "Nueva Factura", para no perder
    las líneas ya cargadas en el formulario principal. No reemplaza a
    CustomerCreateView (el formulario completo sigue existiendo tal cual).
    """
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            return JsonResponse({'ok': True, 'id': customer.id, 'text': str(customer)})
        return JsonResponse({'ok': False, 'errors': form.errors.get_json_data()}, status=400)

    form = CustomerForm()
    return render(request, 'billing/_customer_form_modal.html', {'form': form})


@login_required
def supplier_create_ajax(request):
    """
    Alta rápida de Proveedor desde el modal de "Nueva Compra" (purchasing),
    para no perder las líneas ya cargadas. Vive en billing porque Supplier
    pertenece a esta app. No reemplaza a SupplierCreateView.
    """
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            return JsonResponse({'ok': True, 'id': supplier.id, 'text': str(supplier)})
        return JsonResponse({'ok': False, 'errors': form.errors.get_json_data()}, status=400)

    form = SupplierForm()
    return render(request, 'billing/_supplier_form_modal.html', {'form': form})



# === CUSTOMER (CBV) ===
class CustomerListView(GracefulPaginationMixin, ExportMixin, LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    model = Customer
    template_name = 'billing/customer_list.html'
    context_object_name = 'items'
    paginate_by = 3
    export_filename = 'clientes'
    ALL_COLUMNS = CUSTOMER_ALL_COLUMNS

    def get_active_col_keys(self):
        cols_param = self.request.GET.get('cols', '').strip()
        if cols_param:
            all_keys = {c['key'] for c in self.ALL_COLUMNS}
            valid = [k.strip() for k in cols_param.split(',') if k.strip() in all_keys]
            if valid:
                return valid
        return [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]

    def get_dynamic_export_fields(self):
        active = set(self.get_active_col_keys())
        return [
            col['export']
            for col in self.ALL_COLUMNS
            if col['key'] in active and col.get('export') is not None
        ]

    @property
    def export_fields(self):
        return self.get_dynamic_export_fields()

    def get_queryset(self):
        qs = Customer.objects.all()
        form = CustomerSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('dni'):
                qs = qs.filter(dni__icontains=form.cleaned_data['dni'])
            if form.cleaned_data.get('last_name'):
                qs = qs.filter(last_name__icontains=form.cleaned_data['last_name'])
            if form.cleaned_data.get('first_name'):
                qs = qs.filter(first_name__icontains=form.cleaned_data['first_name'])
            if form.cleaned_data.get('email'):
                qs = qs.filter(email__icontains=form.cleaned_data['email'])
            if form.cleaned_data.get('phone'):
                qs = qs.filter(phone__icontains=form.cleaned_data['phone'])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_form'] = CustomerSearchForm(self.request.GET)
        ctx['all_columns'] = self.ALL_COLUMNS
        ctx['all_col_keys_json'] = json.dumps([c['key'] for c in self.ALL_COLUMNS])
        ctx['default_col_keys_json'] = json.dumps(
            [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]
        )
        return ctx

class CustomerCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Customer;
    form_class = CustomerForm;
    template_name = 'billing/customer_form.html';
    success_url = reverse_lazy('billing:customer_list')
    permission_required = 'billing.add_customer'
    permission_redirect_url = '/customers/'
class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Customer;
    form_class = CustomerForm;
    template_name = 'billing/customer_form.html';
    success_url = reverse_lazy('billing:customer_list')
    permission_required = 'billing.change_customer'
    permission_redirect_url = '/customers/'
class CustomerDeleteView(SuccessUrlPreservePageMixin, LoginRequiredMixin, StaffRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Customer;
    template_name = 'billing/customer_confirm_delete.html';
    success_url = reverse_lazy('billing:customer_list')
    staff_redirect_url = '/customers/'
    permission_required = 'billing.delete_customer'
    permission_redirect_url = '/customers/'

class CustomerDetailView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, DetailView):
    model = Customer
    template_name = 'billing/customer_detail.html'
    context_object_name = 'customer'


# === CONFIGURACIÓN DEL SISTEMA (solo Administrador) ===
class ConfiguracionUpdateView(AdminOnlyMixin, UpdateView):
    model = ConfiguracionSistema
    form_class = ConfiguracionForm
    template_name = 'billing/configuracion_form.html'
    success_url = reverse_lazy('billing:configuracion')

    def get_object(self, queryset=None):
        return ConfiguracionSistema.get_activa()

    def form_valid(self, form):
        messages.success(self.request, 'Configuración actualizada correctamente.')
        return super().form_valid(form)


# === INVOICE (CBV) ===
class InvoiceListView(GracefulPaginationMixin, ExportMixin, LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    model = Invoice
    template_name = 'billing/invoice_list.html'
    context_object_name = 'items'
    paginate_by = 3
    export_filename = 'facturas'
    ALL_COLUMNS = INVOICE_ALL_COLUMNS

    def get_active_col_keys(self):
        cols_param = self.request.GET.get('cols', '').strip()
        if cols_param:
            all_keys = {c['key'] for c in self.ALL_COLUMNS}
            valid = [k.strip() for k in cols_param.split(',') if k.strip() in all_keys]
            if valid:
                return valid
        return [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]

    def get_dynamic_export_fields(self):
        active = set(self.get_active_col_keys())
        return [
            col['export']
            for col in self.ALL_COLUMNS
            if col['key'] in active and col.get('export') is not None
        ]

    @property
    def export_fields(self):
        return self.get_dynamic_export_fields()

    def get_queryset(self):
        qs = Invoice.objects.select_related('customer').order_by('-invoice_date')
        form = InvoiceSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('customer'):
                q = form.cleaned_data['customer']
                qs = qs.filter(
                    Q(customer__first_name__icontains=q) |
                    Q(customer__last_name__icontains=q) |
                    Q(customer__dni__icontains=q)
                )
            if form.cleaned_data.get('date_from'):
                qs = qs.filter(invoice_date__date__gte=form.cleaned_data['date_from'])
            if form.cleaned_data.get('date_to'):
                qs = qs.filter(invoice_date__date__lte=form.cleaned_data['date_to'])
            if form.cleaned_data.get('total_min') is not None:
                qs = qs.filter(total__gte=form.cleaned_data['total_min'])
            if form.cleaned_data.get('total_max') is not None:
                qs = qs.filter(total__lte=form.cleaned_data['total_max'])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_form'] = InvoiceSearchForm(self.request.GET)
        ctx['all_columns'] = self.ALL_COLUMNS
        ctx['all_col_keys_json'] = json.dumps([c['key'] for c in self.ALL_COLUMNS])
        ctx['default_col_keys_json'] = json.dumps(
            [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]
        )
        return ctx
@login_required
@permission_required_with_message('billing.add_invoice', redirect_url='/invoices/')
def invoice_create(request):
    config = ConfiguracionSistema.get_activa()
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceDetailFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    invoice = form.save()
                    formset.instance = invoice
                    formset.save()

                    # Revalida el stock DENTRO de la transacción, con
                    # select_for_update(): cierra la ventana de condición de
                    # carrera entre dos facturas simultáneas que pasaron la
                    # validación del formset (sin locking) antes de que
                    # ninguna hubiera descontado stock todavía. Si algo no
                    # alcanza, se hace rollback completo (ni factura ni stock
                    # quedan modificados a medias).
                    errores_stock = []
                    for d in invoice.details.all():
                        product = Product.objects.select_for_update().get(pk=d.product_id)
                        if d.quantity > product.stock:
                            errores_stock.append(
                                f'"{product.name}": pediste {d.quantity}, pero solo hay {product.stock} en stock.'
                            )
                        else:
                            product.stock = F('stock') - d.quantity
                            product.save(update_fields=['stock'])
                    if errores_stock:
                        raise ValidationError(errores_stock)

                    subtotal = sum(d.subtotal for d in invoice.details.all())
                    invoice.subtotal = subtotal
                    invoice.tax = subtotal * config.iva_porcentaje / Decimal('100')
                    invoice.total = invoice.subtotal + invoice.tax
                    invoice.saldo = invoice.total

                    if invoice.tipo_pago == 'CREDITO':
                        invoice.estado = 'PENDIENTE'
                        invoice.save()
                        from creditos_ventas.services import generar_cuotas
                        generar_cuotas(invoice, form.cleaned_data['num_cuotas'])
                    elif invoice.metodo_pago == 'PAYPAL':
                        # CONTADO + PayPal: todavía NO está pagada. Falta
                        # que el cliente confirme el pago en la ventana de
                        # PayPal, eso pasa en 2 pasos aparte (ver
                        # invoice_paypal_create_order / _capture_order más
                        # abajo). Por eso la dejamos PENDIENTE por ahora.
                        invoice.estado = 'PENDIENTE'
                        invoice.save()
                    else:
                        # CONTADO en efectivo/transferencia: no hay pasarela
                        # de pago real, se confía en el cajero y el pago
                        # queda confirmado de inmediato (igual que antes).
                        invoice.saldo = 0
                        invoice.estado = 'PAGADA'
                        invoice.save()
                        from shared.sri_client import emitir_factura_sri
                        emitir_factura_sri(invoice)
            except ValidationError as e:
                for msg in e.messages:
                    messages.error(request, msg)
                return redirect('billing:invoice_create')

            if invoice.tipo_pago == 'CONTADO' and invoice.metodo_pago == 'PAYPAL':
                # Manda al cliente a la pantalla de detalle, donde va a
                # aparecer el botón de PayPal para terminar de pagar.
                messages.info(
                    request,
                    f'Factura #{invoice.id} creada por ${invoice.total}. '
                    f'Completa el pago con PayPal para confirmarla.'
                )
                return redirect('billing:invoice_detail', pk=invoice.pk)

            # Correo con la factura en PDF al cliente (si tiene correo registrado).
            # Try/except SEPARADO de la transacción de guardado de arriba: la
            # factura ya quedó guardada en la BD en ese punto, así que si el
            # envío falla (SMTP caído, credenciales, etc.) eso no debe tumbar
            # la respuesta con un 500 -- el usuario tiene que ver un mensaje
            # claro, no una pantalla de error, sobre una factura que sí se creó.
            pdf_bytes = generar_pdf_factura(invoice)
            try:
                enviado = send_invoice_email(invoice, pdf_bytes)
            except Exception:
                logger.exception('Fallo al enviar por correo la factura #%s', invoice.id)
                enviado = None  # distinto de False: "sin correo" vs "falló el envío"

            if enviado:
                invoice.enviado_email = True
                invoice.fecha_envio_email = timezone.now()
                invoice.save(update_fields=['enviado_email', 'fecha_envio_email'])

            if enviado:
                messages.success(
                    request,
                    f'Factura #{invoice.id} creada! Total: ${invoice.total}. '
                    f'Se envió por correo a {invoice.customer.email}.'
                )
            elif enviado is None:
                messages.warning(
                    request,
                    f'Factura #{invoice.id} creada! Total: ${invoice.total}. '
                    f'No se pudo enviar el correo en este momento; intenta reenviarla más tarde.'
                )
            else:
                messages.warning(
                    request,
                    f'Factura #{invoice.id} creada! Total: ${invoice.total}. '
                    f'El cliente no tiene correo registrado, no se envió factura por email.'
                )
            return redirect('billing:invoice_list')
    else:
        form = InvoiceForm()
        formset = InvoiceDetailFormSet()
    return render(request, 'billing/invoice_form.html', {
        'form': form, 'formset': formset, 'title': 'Nueva Factura', 'config': config,
    })


class InvoiceDeleteView(SuccessUrlPreservePageMixin, ProtectedDeleteMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Invoice
    template_name = 'billing/invoice_confirm_delete.html'
    success_url = reverse_lazy('billing:invoice_list')
    protected_message = 'No se puede eliminar la factura porque tiene cuotas de crédito asociadas.'
    permission_required = 'billing.delete_invoice'
    permission_redirect_url = '/invoices/'

    def before_delete(self, invoice):
        # invoice_create descuenta stock al crear (ver más abajo); si la
        # factura se elimina, hay que devolverlo. Las CREDITO con cuotas
        # nunca llegan hasta acá: CuotaVenta.factura es PROTECT, así que
        # delete() ya las bloquea antes de este hook -- no hay riesgo de
        # restaurar stock dos veces sobre la misma factura.
        for d in invoice.details.select_related('product'):
            Product.objects.filter(pk=d.product_id).update(stock=F('stock') + d.quantity)


@login_required
@any_crud_permission_required('billing', 'invoice', redirect_url='/invoices/')
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product'),
        pk=pk,
    )
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'paypal_client_id': settings.PAYPAL_CLIENT_ID,
    })


@login_required
@permission_required_with_message('billing.imprimir_factura', redirect_url='/invoices/')
def invoice_pdf_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    pdf_bytes = generar_pdf_factura(invoice)
    return HttpResponse(pdf_bytes, content_type='application/pdf')


@login_required
@permission_required_with_message('billing.add_invoice', redirect_url='/invoices/')
def invoice_paypal_create_order(request, pk):
    """
    Endpoint AJAX: el botón de PayPal (JS) lo llama para pedir un
    order_id ANTES de abrir la ventana de checkout. Solo aplica a
    facturas de contado que eligieron PayPal y que todavía no están
    pagadas (evita crear una orden nueva sobre una factura ya cerrada).
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    if invoice.metodo_pago != 'PAYPAL' or invoice.estado == 'PAGADA':
        return JsonResponse(
            {'error': 'Esta factura no admite pago con PayPal en este momento.'}, status=400
        )
    try:
        order = create_paypal_order(
            invoice.total,
            description=f'Factura #{invoice.id} - Sistema de Ventas'
        )
    except PayPalError as e:
        return JsonResponse({'error': str(e)}, status=502)

    invoice.paypal_order_id = order['id']
    invoice.paypal_status = 'CREATED'
    invoice.save(update_fields=['paypal_order_id', 'paypal_status'])
    return JsonResponse({'id': order['id']})


@login_required
@permission_required_with_message('billing.add_invoice', redirect_url='/invoices/')
def invoice_paypal_capture_order(request, pk):
    """
    Endpoint AJAX: el botón de PayPal lo llama justo después de que el
    cliente aprobó el pago en su ventana. Aquí se confirma el cobro real
    y recién aquí se marca la factura como PAGADA.
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    if not invoice.paypal_order_id:
        return JsonResponse({'error': 'Esta factura no tiene una orden de PayPal creada.'}, status=400)

    try:
        capture = capture_paypal_order(invoice.paypal_order_id)
    except PayPalError as e:
        return JsonResponse({'error': str(e)}, status=502)

    data = extract_capture_data(capture)
    invoice.paypal_capture_id = data['capture_id']
    invoice.paypal_status = data['status']
    invoice.paypal_payer_email = data['payer_email']

    if data['status'] != 'COMPLETED':
        invoice.save()
        return JsonResponse(
            {'error': f'PayPal no completó el pago (estado: {data["status"]}).'}, status=400
        )

    invoice.estado = 'PAGADA'
    invoice.saldo = 0
    invoice.save()

    from shared.sri_client import emitir_factura_sri
    emitir_factura_sri(invoice)

    # El pago ya quedó confirmado y guardado arriba -- si el correo falla
    # (SMTP caído, etc.) no debe tumbar esta respuesta con un 500, el pago
    # sigue siendo válido de todos modos.
    pdf_bytes = generar_pdf_factura(invoice)
    try:
        enviado = send_invoice_email(invoice, pdf_bytes)
    except Exception:
        logger.exception('Fallo al enviar por correo la factura #%s tras confirmar PayPal', invoice.id)
        enviado = None
    if enviado:
        invoice.enviado_email = True
        invoice.fecha_envio_email = timezone.now()
        invoice.save(update_fields=['enviado_email', 'fecha_envio_email'])

    return JsonResponse({'status': 'COMPLETED'})


@login_required
@permission_required_with_message('billing.cancelar_invoice_paypal', redirect_url='/invoices/')
def invoice_cancel_paypal(request, pk):
    """
    Cancela una factura CONTADO+PayPal que quedó PENDIENTE porque el
    cliente nunca completó el pago en la ventana de PayPal: restaura el
    stock que invoice_create ya había descontado al crearla y marca la
    factura CANCELADA. Solo aplica a facturas PayPal todavía pendientes --
    una ya PAGADA no puede cancelarse por este camino (invoice_paypal_
    capture_order es el único lugar que las marca PAGADA).
    """
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.tipo_pago != 'CONTADO' or invoice.metodo_pago != 'PAYPAL' or invoice.estado != 'PENDIENTE':
        messages.error(
            request,
            'Esta factura no se puede cancelar por este camino (solo aplica a '
            'facturas de contado con PayPal que sigan pendientes de pago).'
        )
        return redirect('billing:invoice_detail', pk=invoice.pk)

    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=invoice.pk)

    with transaction.atomic():
        for d in invoice.details.select_related('product'):
            Product.objects.filter(pk=d.product_id).update(stock=F('stock') + d.quantity)
        invoice.estado = 'CANCELADA'
        invoice.save(update_fields=['estado'])

    messages.success(request, f'Factura #{invoice.id} cancelada. El stock reservado fue restaurado.')
    return redirect('billing:invoice_detail', pk=invoice.pk)
