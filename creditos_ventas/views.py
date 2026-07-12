from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, DeleteView

from billing.models import Invoice
from shared.mixins import ProtectedDeleteMixin

from .models import CuotaVenta, PagoCuotaVenta
from .forms import PagoCuotaVentaForm
from .services import recalcular_cuota, recalcular_factura


# === CUOTAS ===

class CuotaListView(LoginRequiredMixin, ListView):
    """Cuotas de UNA factura específica."""
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_list.html'
    context_object_name = 'cuotas'

    def get_queryset(self):
        self.factura = get_object_or_404(Invoice, pk=self.kwargs['pk'])
        return CuotaVenta.objects.filter(factura=self.factura)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['factura'] = self.factura
        return ctx


class CuotaPendientesListView(LoginRequiredMixin, ListView):
    """Todas las cuotas PENDIENTES del sistema, sin importar la factura."""
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_pendientes_list.html'
    context_object_name = 'cuotas'

    def get_queryset(self):
        return (
            CuotaVenta.objects
            .filter(estado='PENDIENTE')
            .select_related('factura', 'factura__customer')
            .order_by('fecha_vencimiento')
        )


class CuotaDeleteView(ProtectedDeleteMixin, LoginRequiredMixin, DeleteView):
    """
    Elimina una cuota. PagoCuotaVenta.cuota usa on_delete=PROTECT, así que
    si la cuota ya tiene pagos registrados, ProtectedDeleteMixin lo bloquea
    con un mensaje amigable en vez de un 500.
    """
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_confirm_delete.html'
    protected_message = 'No se puede eliminar la cuota porque tiene pagos registrados.'
    success_message = 'Cuota eliminada correctamente.'

    def get_success_url(self):
        return reverse('creditos_ventas:cuotas_factura', kwargs={'pk': self.object.factura_id})


# === PAGOS ===

@login_required
def registrar_pago(request, cuota_pk):
    """Registra un pago sobre una cuota y recalcula cuota + factura."""
    cuota = get_object_or_404(CuotaVenta, pk=cuota_pk)

    if cuota.estado == 'PAGADA':
        messages.error(request, 'Esta cuota ya está pagada por completo, no admite más pagos.')
        return redirect('creditos_ventas:cuotas_factura', pk=cuota.factura_id)

    if request.method == 'POST':
        form = PagoCuotaVentaForm(request.POST, cuota=cuota)
        if form.is_valid():
            with transaction.atomic():
                pago = form.save(commit=False)
                pago.cuota = cuota
                pago.save()
                recalcular_cuota(cuota)
                recalcular_factura(cuota.factura)
            messages.success(
                request,
                f'Pago de ${pago.valor} registrado en la cuota {cuota.numero} de la factura #{cuota.factura_id}.'
            )
            return redirect('creditos_ventas:cuotas_factura', pk=cuota.factura_id)
    else:
        form = PagoCuotaVentaForm(cuota=cuota, initial={'fecha': timezone.localdate()})

    return render(request, 'creditos_ventas/registrar_pago.html', {'form': form, 'cuota': cuota})


class HistorialPagosCuotaView(LoginRequiredMixin, ListView):
    """Historial de pagos de UNA cuota."""
    model = PagoCuotaVenta
    template_name = 'creditos_ventas/historial_pagos.html'
    context_object_name = 'pagos'

    def get_queryset(self):
        self.cuota = get_object_or_404(CuotaVenta, pk=self.kwargs['pk'])
        return PagoCuotaVenta.objects.filter(cuota=self.cuota).order_by('-fecha', '-id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cuota'] = self.cuota
        ctx['factura'] = self.cuota.factura
        return ctx


class HistorialPagosFacturaView(LoginRequiredMixin, ListView):
    """Historial de pagos de TODAS las cuotas de una factura."""
    model = PagoCuotaVenta
    template_name = 'creditos_ventas/historial_pagos.html'
    context_object_name = 'pagos'

    def get_queryset(self):
        self.factura = get_object_or_404(Invoice, pk=self.kwargs['pk'])
        return (
            PagoCuotaVenta.objects
            .filter(cuota__factura=self.factura)
            .select_related('cuota')
            .order_by('cuota__numero', '-fecha')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['factura'] = self.factura
        ctx['cuota'] = None
        return ctx
