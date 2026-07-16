import json
import logging
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db import transaction
from django.db.models import ProtectedError
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.db.models import Avg, Sum, Count, F

from billing.mixins import ExportMixin
from billing.models import Product, ConfiguracionSistema
from shared.mixins import (
    PermissionRequiredMixin, redirect_preserving_page, GracefulPaginationMixin,
    AnyCrudPermissionRequiredMixin,
)
from shared.decorators import permission_required_with_message, any_crud_permission_required
from .models import Purchase, PurchaseDetail
from .forms import PurchaseForm, PurchaseDetailFormSet, PurchaseSearchForm
from .purchase_pdf import generar_pdf_compra
from shared.emails import send_purchase_email

logger = logging.getLogger(__name__)


# ── Columnas disponibles para Compras ──
PURCHASE_ALL_COLUMNS = [
    {'key': 'id',              'label': 'N° Compra',    'default': True,
     'export': ('id', 'N° Compra')},
    {'key': 'supplier',        'label': 'Proveedor',    'default': True,
     'export': (lambda obj: obj.supplier.name, 'Proveedor')},
    {'key': 'document_number', 'label': 'N° Documento', 'default': True,
     'export': ('document_number', 'N° Documento')},
    {'key': 'purchase_date',   'label': 'Fecha',        'default': True,
     'export': (lambda obj: obj.purchase_date.strftime('%d/%m/%Y %H:%M'), 'Fecha')},
    {'key': 'subtotal',        'label': 'Subtotal',     'default': True,
     'export': ('subtotal', 'Subtotal ($)')},
    {'key': 'tax',             'label': 'IVA',          'default': True,
     'export': ('tax', 'IVA ($)')},
    {'key': 'total',           'label': 'Total',        'default': True,
     'export': ('total', 'Total ($)')},
]


# === PURCHASE LIST (CBV con export, igual que InvoiceListView) ===
class PurchaseListView(GracefulPaginationMixin, ExportMixin, LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    model = Purchase
    template_name = 'purchasing/purchase_list.html'
    context_object_name = 'items'
    paginate_by = 3
    export_filename = 'compras'
    ALL_COLUMNS = PURCHASE_ALL_COLUMNS

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
        return [c['export'] for c in self.ALL_COLUMNS
                if c['key'] in active and c.get('export') is not None]

    @property
    def export_fields(self):
        return self.get_dynamic_export_fields()

    def get_queryset(self):
        qs = Purchase.objects.select_related('supplier').order_by('-purchase_date')
        form = PurchaseSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('supplier'):
                qs = qs.filter(supplier__name__icontains=form.cleaned_data['supplier'])
            if form.cleaned_data.get('document_number'):
                qs = qs.filter(document_number__icontains=form.cleaned_data['document_number'])
            if form.cleaned_data.get('date_from'):
                qs = qs.filter(purchase_date__date__gte=form.cleaned_data['date_from'])
            if form.cleaned_data.get('date_to'):
                qs = qs.filter(purchase_date__date__lte=form.cleaned_data['date_to'])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_form'] = PurchaseSearchForm(self.request.GET)
        ctx['all_columns'] = self.ALL_COLUMNS
        ctx['all_col_keys_json'] = json.dumps([c['key'] for c in self.ALL_COLUMNS])
        ctx['default_col_keys_json'] = json.dumps(
            [c['key'] for c in self.ALL_COLUMNS if c.get('default', True)]
        )
        return ctx


# === CREATE (FBV con formset) ===
@login_required
@permission_required_with_message('purchasing.add_purchase', redirect_url='/purchases/')
def purchase_create(request):
    """Crea una compra con sus líneas de detalle."""
    config = ConfiguracionSistema.get_activa()
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        formset = PurchaseDetailFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            # Todo el flujo de creación (cabecera + líneas + stock + totales
            # + cuotas) va en UN solo atomic(): antes solo la parte de
            # estado/saldo/cuotas estaba protegida, así que si generar_cuotas
            # fallaba a mitad de camino, la Purchase, sus PurchaseDetail y el
            # stock ya incrementado quedaban guardados de todos modos --
            # huérfanos, sin cuotas. Mismo patrón que invoice_create.
            with transaction.atomic():
                purchase = form.save()
                formset.instance = purchase
                formset.save()

                # Reto 10.1 — la compra SUMA stock
                for d in purchase.details.all():
                    Product.objects.filter(pk=d.product_id).update(stock=F('stock') + d.quantity)

                # Totales
                subtotal = sum(d.subtotal for d in purchase.details.all())
                purchase.subtotal = subtotal
                purchase.tax = subtotal * config.iva_porcentaje / Decimal('100')
                purchase.total = purchase.subtotal + purchase.tax

                if purchase.tipo_pago == 'CONTADO':
                    purchase.saldo = 0
                    purchase.estado = 'PAGADA'
                else:  # CREDITO
                    purchase.saldo = purchase.total
                    purchase.estado = 'PENDIENTE'
                purchase.save()

                if purchase.tipo_pago == 'CREDITO':
                    from creditos_compras.services import generar_cuotas
                    generar_cuotas(purchase, form.cleaned_data['num_cuotas'])

            # Correo con la orden de compra en PDF al proveedor (si tiene correo
            # registrado). Try/except SEPARADO de la transacción de guardado
            # de arriba: la compra ya quedó guardada, así que si el envío
            # falla (SMTP caído, etc.) eso no debe tumbar la respuesta con un
            # 500 -- el usuario tiene que ver un mensaje claro, no una
            # pantalla de error, sobre una compra que sí se creó.
            pdf_bytes = generar_pdf_compra(purchase)
            try:
                enviado = send_purchase_email(purchase, pdf_bytes)
            except Exception:
                logger.exception('Fallo al enviar por correo la compra #%s', purchase.id)
                enviado = None  # distinto de False: "sin correo" vs "falló el envío"

            if enviado:
                messages.success(
                    request,
                    f'Compra #{purchase.id} creada! Total: ${purchase.total}. '
                    f'Se envió por correo a {purchase.supplier.email}.'
                )
            elif enviado is None:
                messages.warning(
                    request,
                    f'Compra #{purchase.id} creada! Total: ${purchase.total}. '
                    f'No se pudo enviar el correo en este momento; intenta reenviarla más tarde.'
                )
            else:
                messages.warning(
                    request,
                    f'Compra #{purchase.id} creada! Total: ${purchase.total}. '
                    f'El proveedor no tiene correo registrado, no se envió la orden por email.'
                )
            return redirect('purchasing:purchase_list')
    else:
        form = PurchaseForm()
        formset = PurchaseDetailFormSet()
    return render(request, 'purchasing/purchase_form.html', {
        'form': form, 'formset': formset, 'title': 'Nueva Compra', 'config': config,
    })


# === DETAIL (FBV) ===
@login_required
@any_crud_permission_required('purchasing', 'purchase', redirect_url='/')
def purchase_detail(request, pk):
    """Muestra el detalle completo de una compra."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier')
                        .prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'purchasing/purchase_detail.html', {'purchase': purchase})


@login_required
@permission_required_with_message('purchasing.imprimir_orden_compra', redirect_url='/')
def purchase_pdf_view(request, pk):
    """Genera el PDF de la compra para imprimir/verla en el navegador."""
    purchase = get_object_or_404(Purchase, pk=pk)
    pdf_bytes = generar_pdf_compra(purchase)
    return HttpResponse(pdf_bytes, content_type='application/pdf')


# === DELETE (FBV) ===
@login_required
@permission_required_with_message('purchasing.delete_purchase', redirect_url='/purchases/')
def purchase_delete(request, pk):
    """Elimina una compra y todas sus líneas (CASCADE)."""
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        purchase_id = purchase.id
        try:
            with transaction.atomic():
                # purchase_create suma stock al crear (ver más abajo); si la
                # compra se elimina, hay que devolverlo (restarlo). Las
                # CREDITO con cuotas nunca llegan hasta acá: CuotaCompra.compra
                # es PROTECT, así que delete() ya las bloquea antes de este
                # bucle -- si eso llegara a pasar, el atomic() revierte esta
                # resta también, no queda stock descontado dos veces.
                for d in purchase.details.select_related('product'):
                    Product.objects.filter(pk=d.product_id).update(stock=F('stock') - d.quantity)
                purchase.delete()
            messages.success(request, f'Compra #{purchase_id} eliminada!')
        except ProtectedError:
            messages.error(request, 'No se puede eliminar la compra porque tiene cuotas de crédito asociadas.')
        return redirect_preserving_page(request, 'purchasing:purchase_list')
    return render(request, 'purchasing/purchase_confirm_delete.html', {'object': purchase})


# === REPORT (FBV con agregación) ===
@login_required
@permission_required_with_message('purchasing.view_purchase_report', redirect_url='/purchases/')
def purchase_report(request):
    """Reporte: costo promedio, total comprado y N° de compras por producto."""
    report = (
        PurchaseDetail.objects
        .values('product__name')
        .annotate(
            avg_cost=Avg('unit_cost'),
            total_qty=Sum('quantity'),
            times_bought=Count('id'),
            total_spent=Sum('subtotal'),
        )
        .order_by('-total_spent')
    )
    return render(request, 'purchasing/purchase_report.html', {'report': report})