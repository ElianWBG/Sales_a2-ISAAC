from decimal import Decimal
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, DeleteView

from purchasing.models import Purchase
from shared.mixins import ProtectedDeleteMixin

from .models import CuotaCompra, PagoCuotaCompra
from .forms import PagoCuotaCompraForm
from .services import recalcular_cuota, recalcular_compra
from .plan_pagos_pdf import generar_pdf_plan_pagos_compra


# === CUOTAS ===

class CuotaListView(LoginRequiredMixin, ListView):
    """Cuotas de UNA compra específica."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_list.html'
    context_object_name = 'cuotas'

    def get_queryset(self):
        self.compra = get_object_or_404(Purchase, pk=self.kwargs['pk'])
        return CuotaCompra.objects.filter(compra=self.compra)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['compra'] = self.compra
        return ctx


class CuotaPendientesListView(LoginRequiredMixin, ListView):
    """Todas las cuotas PENDIENTES del sistema, sin importar la compra."""
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_pendientes_list.html'
    context_object_name = 'cuotas'

    def get_queryset(self):
        return (
            CuotaCompra.objects
            .filter(estado='PENDIENTE')
            .select_related('compra', 'compra__supplier')
            .order_by('fecha_vencimiento')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['hoy'] = timezone.localdate()
        return ctx


class CuotaDeleteView(ProtectedDeleteMixin, LoginRequiredMixin, DeleteView):
    """
    Elimina una cuota. PagoCuotaCompra.cuota usa on_delete=PROTECT, así que
    si la cuota ya tiene pagos registrados, ProtectedDeleteMixin lo bloquea
    con un mensaje amigable en vez de un 500.
    """
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_confirm_delete.html'
    protected_message = 'No se puede eliminar la cuota porque tiene pagos registrados.'
    success_message = 'Cuota eliminada correctamente.'

    def get_success_url(self):
        return reverse('creditos_compras:cuotas_compra', kwargs={'pk': self.object.compra_id})


# === PAGOS ===

@login_required
def registrar_pago(request, cuota_pk):
    """Registra un pago sobre una cuota y recalcula cuota + compra."""
    cuota = get_object_or_404(CuotaCompra, pk=cuota_pk)

    if cuota.estado == 'PAGADA':
        messages.error(request, 'Esta cuota ya está pagada por completo, no admite más pagos.')
        return redirect('creditos_compras:cuotas_compra', pk=cuota.compra_id)

    if request.method == 'POST':
        form = PagoCuotaCompraForm(request.POST, cuota=cuota)
        if form.is_valid():
            with transaction.atomic():
                pago = form.save(commit=False)
                pago.cuota = cuota
                pago.save()
                recalcular_cuota(cuota)
                recalcular_compra(cuota.compra)
            messages.success(
                request,
                f'Pago de ${pago.valor} registrado en la cuota {cuota.numero} de la compra #{cuota.compra_id}.'
            )
            return redirect('creditos_compras:cuotas_compra', pk=cuota.compra_id)
    else:
        form = PagoCuotaCompraForm(cuota=cuota, initial={'fecha': timezone.localdate()})

    return render(request, 'creditos_compras/registrar_pago.html', {'form': form, 'cuota': cuota})


@login_required
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

    fecha_compra = purchase.purchase_date.date() if hasattr(purchase.purchase_date, 'date') else purchase.purchase_date
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
            total_pagado = Decimal('0')
            for cuota in cuotas:
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


class HistorialPagosCuotaView(LoginRequiredMixin, ListView):
    """Historial de pagos de UNA cuota."""
    model = PagoCuotaCompra
    template_name = 'creditos_compras/historial_pagos.html'
    context_object_name = 'pagos'

    def get_queryset(self):
        self.cuota = get_object_or_404(CuotaCompra, pk=self.kwargs['pk'])
        return PagoCuotaCompra.objects.filter(cuota=self.cuota).select_related('cuota').order_by('-fecha', '-id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cuota'] = self.cuota
        ctx['compra'] = self.cuota.compra
        return ctx


class HistorialPagosCompraView(LoginRequiredMixin, ListView):
    """Historial de pagos de TODAS las cuotas de una compra."""
    model = PagoCuotaCompra
    template_name = 'creditos_compras/historial_pagos.html'
    context_object_name = 'pagos'

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
def plan_pagos_pdf_view(request, purchase_pk):
    """Genera el PDF del Plan de Pagos / Estado de Cuenta de una compra a crédito."""
    purchase = get_object_or_404(Purchase, pk=purchase_pk)
    pdf_bytes = generar_pdf_plan_pagos_compra(purchase)
    return HttpResponse(pdf_bytes, content_type='application/pdf')
