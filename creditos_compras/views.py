from decimal import Decimal
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, DeleteView

from purchasing.models import Purchase
from shared.mixins import ProtectedDeleteMixin, PermissionRequiredMixin, AnyCrudPermissionRequiredMixin
from shared.decorators import permission_required_with_message, any_crud_permission_required

from .models import CuotaCompra, PagoCuotaCompra
from .forms import PagoCuotaCompraForm, CuotaCompraPendienteSearchForm
from .services import recalcular_cuota, recalcular_compra
from .plan_pagos_pdf import generar_pdf_plan_pagos_compra


# === CUOTAS ===

class CuotaListView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    """Cuotas de UNA compra específica."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_list.html'
    context_object_name = 'cuotas'
    # add/change/delete son decorativos en CuotaCompra y están ocultos en la
    # matriz de permisos (ACTIONS_EXCLUDED_PER_MODEL) -- mismo motivo que
    # creditos_ventas.CuotaListView.crud_actions. Ver es la única acción real.
    crud_actions = ('view',)

    def get_queryset(self):
        self.compra = get_object_or_404(Purchase, pk=self.kwargs['pk'])
        return CuotaCompra.objects.filter(compra=self.compra)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['compra'] = self.compra
        return ctx


class CuotaPendientesListView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    """Todas las cuotas PENDIENTES del sistema, sin importar la compra."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_pendientes_list.html'
    context_object_name = 'cuotas'
    crud_actions = ('view',)  # mismo motivo que CuotaListView

    def get_queryset(self):
        qs = (
            CuotaCompra.objects
            .filter(estado='PENDIENTE')
            .select_related('compra', 'compra__supplier')
            .order_by('fecha_vencimiento')
        )
        form = CuotaCompraPendienteSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('proveedor'):
                qs = qs.filter(compra__supplier__name__icontains=form.cleaned_data['proveedor'])
            if form.cleaned_data.get('fecha_desde'):
                qs = qs.filter(fecha_vencimiento__gte=form.cleaned_data['fecha_desde'])
            if form.cleaned_data.get('fecha_hasta'):
                qs = qs.filter(fecha_vencimiento__lte=form.cleaned_data['fecha_hasta'])
            estado = form.cleaned_data.get('estado')
            if estado == 'PENDIENTE':
                qs = qs.filter(saldo=F('valor'))
            elif estado == 'PARCIAL':
                qs = qs.filter(saldo__lt=F('valor'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['hoy'] = timezone.localdate()
        ctx['search_form'] = CuotaCompraPendienteSearchForm(self.request.GET)
        return ctx


class CuotaDeleteView(ProtectedDeleteMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """
    Elimina una cuota. PagoCuotaCompra.cuota usa on_delete=PROTECT, así que
    si la cuota ya tiene pagos registrados, ProtectedDeleteMixin lo bloquea
    con un mensaje amigable en vez de un 500.
    """
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_confirm_delete.html'
    protected_message = 'No se puede eliminar la cuota porque tiene pagos registrados.'
    success_message = 'Cuota eliminada correctamente.'
    permission_required = 'creditos_compras.delete_cuotacompra'
    permission_redirect_url = '/'

    def get_success_url(self):
        return reverse('creditos_compras:cuotas_compra', kwargs={'pk': self.object.compra_id})


# === PAGOS ===

@login_required
@permission_required_with_message('creditos_compras.add_pagocuotacompra', redirect_url='/')
def registrar_pago(request, cuota_pk):
    """Registra un pago sobre una cuota y recalcula cuota + compra."""
    cuota = get_object_or_404(CuotaCompra, pk=cuota_pk)

    if cuota.estado == 'PAGADA':
        messages.error(request, 'Esta cuota ya está pagada por completo, no admite más pagos.')
        return redirect('creditos_compras:cuotas_compra', pk=cuota.compra_id)

    if request.method == 'POST':
        # select_for_update() DENTRO de la transacción, ANTES de armar/validar
        # el form: PagoCuotaCompraForm.clean_valor compara `valor` contra
        # `cuota.saldo`, así que ese saldo tiene que venir de la fila ya
        # bloqueada -- si se bloqueara después de validar, dos pagos
        # concurrentes ya habrían leído el mismo saldo stale y ambos
        # pasarían la validación (mismo patrón que select_for_update()
        # sobre Product en invoice_create).
        with transaction.atomic():
            cuota_locked = CuotaCompra.objects.select_for_update().get(pk=cuota.pk)

            if cuota_locked.estado == 'PAGADA':
                messages.error(request, 'Esta cuota ya está pagada por completo, no admite más pagos.')
                return redirect('creditos_compras:cuotas_compra', pk=cuota_locked.compra_id)

            form = PagoCuotaCompraForm(request.POST, cuota=cuota_locked)
            if form.is_valid():
                pago = form.save(commit=False)
                pago.cuota = cuota_locked
                pago.save()
                recalcular_cuota(cuota_locked)
                recalcular_compra(cuota_locked.compra)
                messages.success(
                    request,
                    f'Pago de ${pago.valor} registrado en la cuota {cuota_locked.numero} de la compra #{cuota_locked.compra_id}.'
                )
                return redirect('creditos_compras:cuotas_compra', pk=cuota_locked.compra_id)
    else:
        form = PagoCuotaCompraForm(cuota=cuota, initial={'fecha': timezone.localdate()})

    return render(request, 'creditos_compras/registrar_pago.html', {'form': form, 'cuota': cuota})


@login_required
@permission_required_with_message('creditos_compras.add_pagocuotacompra', redirect_url='/')
def pagar_cuotas_lote(request, purchase_pk):
    """
    Paga el saldo COMPLETO de varias cuotas de una misma compra en un
    solo lote (un PagoCuotaCompra por cuota, misma fecha para todas).
    No reemplaza el pago individual: coexisten ambos flujos.
    """
    purchase = get_object_or_404(Purchase, pk=purchase_pk)

    if request.method != 'POST':
        return redirect('creditos_compras:cuotas_compra', pk=purchase.pk)

    cuota_ids = request.POST.getlist('cuotas')
    fecha_str = request.POST.get('fecha')

    if not cuota_ids:
        messages.error(request, 'No seleccionaste ninguna cuota para pagar.')
        return redirect('creditos_compras:cuotas_compra', pk=purchase.pk)

    try:
        fecha = date.fromisoformat(fecha_str)
    except (TypeError, ValueError):
        messages.error(request, 'La fecha de pago no es válida.')
        return redirect('creditos_compras:cuotas_compra', pk=purchase.pk)

    # .date() crudo trunca en UTC, no en hora local (ver mismo fix en
    # creditos_compras/services.py y forms.py).
    if hasattr(purchase.purchase_date, 'tzinfo') and purchase.purchase_date.tzinfo is not None:
        fecha_compra = timezone.localtime(purchase.purchase_date).date()
    elif hasattr(purchase.purchase_date, 'date'):
        fecha_compra = purchase.purchase_date.date()
    else:
        fecha_compra = purchase.purchase_date
    if fecha > timezone.localdate():
        messages.error(request, 'La fecha de pago no puede ser futura.')
        return redirect('creditos_compras:cuotas_compra', pk=purchase.pk)
    if fecha < fecha_compra:
        messages.error(request, 'La fecha de pago no puede ser anterior a la fecha de la compra.')
        return redirect('creditos_compras:cuotas_compra', pk=purchase.pk)

    cuotas = list(CuotaCompra.objects.filter(pk__in=cuota_ids, compra=purchase))
    encontrados = {str(cu.pk) for cu in cuotas}
    faltantes = [cid for cid in cuota_ids if cid not in encontrados]
    if faltantes:
        messages.error(
            request,
            f'No se procesó el pago: la(s) cuota(s) con ID {", ".join(faltantes)} '
            f'no pertenece(n) a esta compra.'
        )
        return redirect('creditos_compras:cuotas_compra', pk=purchase.pk)

    try:
        with transaction.atomic():
            # select_for_update() DENTRO de la transacción, releyendo las
            # cuotas en vez de reusar la lista de arriba (fetched antes del
            # atomic, sin lock): acá se lee `cuota.saldo` directo para
            # pagarlo completo, así que si esa lectura es stale, dos pagos
            # en lote concurrentes sobre la misma cuota podrían generar dos
            # PagoCuotaCompra por el total (mismo problema que en
            # registrar_pago, incluso sin pasar por el form).
            cuotas_locked = list(
                CuotaCompra.objects.select_for_update().filter(pk__in=encontrados)
            )
            total_pagado = Decimal('0')
            for cuota in cuotas_locked:
                if cuota.estado == 'PAGADA':
                    raise ValueError(f'la cuota {cuota.numero} ya está pagada por completo.')
                valor = cuota.saldo
                PagoCuotaCompra.objects.create(
                    cuota=cuota, fecha=fecha, valor=valor, observacion='Pago en lote',
                )
                recalcular_cuota(cuota)
                total_pagado += valor
            recalcular_compra(purchase)
    except ValueError as e:
        messages.error(request, f'No se procesó el pago en lote: {e}')
        return redirect('creditos_compras:cuotas_compra', pk=purchase.pk)

    messages.success(
        request,
        f'Se pagaron {len(cuotas)} cuota(s) por un total de ${total_pagado}.'
    )
    return redirect('creditos_compras:cuotas_compra', pk=purchase.pk)


class HistorialPagosCuotaView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    """Historial de pagos de UNA cuota."""
    model = PagoCuotaCompra
    template_name = 'creditos_compras/historial_pagos.html'
    context_object_name = 'pagos'
    # "Ver" controla el Historial de forma independiente de "Crear" (que
    # gatea registrar_pago aparte) -- mismo motivo que
    # creditos_ventas.HistorialPagosCuotaView.
    crud_actions = ('view',)

    def get_queryset(self):
        self.cuota = get_object_or_404(CuotaCompra, pk=self.kwargs['pk'])
        return PagoCuotaCompra.objects.filter(cuota=self.cuota).select_related('cuota').order_by('-fecha', '-id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cuota'] = self.cuota
        ctx['compra'] = self.cuota.compra
        return ctx


class HistorialPagosCompraView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    """Historial de pagos de TODAS las cuotas de una compra."""
    model = PagoCuotaCompra
    template_name = 'creditos_compras/historial_pagos.html'
    context_object_name = 'pagos'
    crud_actions = ('view',)  # mismo motivo que HistorialPagosCuotaView

    def get_queryset(self):
        self.compra = get_object_or_404(Purchase, pk=self.kwargs['pk'])
        return (
            PagoCuotaCompra.objects
            .filter(cuota__compra=self.compra)
            .select_related('cuota')
            .order_by('cuota__numero', '-fecha')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['compra'] = self.compra
        ctx['cuota'] = None
        return ctx


# === PDF ===

@login_required
@permission_required_with_message('creditos_compras.imprimir_plan_pagos', redirect_url='/')
def plan_pagos_pdf_view(request, purchase_pk):
    """Genera el PDF del Plan de Pagos / Estado de Cuenta de una compra a crédito."""
    purchase = get_object_or_404(Purchase, pk=purchase_pk)
    pdf_bytes = generar_pdf_plan_pagos_compra(purchase)
    return HttpResponse(pdf_bytes, content_type='application/pdf')
