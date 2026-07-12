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

from billing.models import Invoice
from shared.mixins import ProtectedDeleteMixin

from .models import CuotaVenta, PagoCuotaVenta
from .forms import PagoCuotaVentaForm
from .services import recalcular_cuota, recalcular_factura
from .plan_pagos_pdf import generar_pdf_plan_pagos


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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['hoy'] = timezone.localdate()
        return ctx


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


@login_required
def pagar_cuotas_lote(request, invoice_pk):
    """
    Paga el saldo COMPLETO de varias cuotas de una misma factura en un
    solo lote (un PagoCuotaVenta por cuota, misma fecha para todas).
    No reemplaza el pago individual: coexisten ambos flujos.
    """
    invoice = get_object_or_404(Invoice, pk=invoice_pk)

    if request.method != 'POST':
        return redirect('creditos_ventas:cuotas_factura', pk=invoice.pk)

    cuota_ids = request.POST.getlist('cuotas')
    fecha_str = request.POST.get('fecha')

    if not cuota_ids:
        messages.error(request, 'No seleccionaste ninguna cuota para pagar.')
        return redirect('creditos_ventas:cuotas_factura', pk=invoice.pk)

    try:
        fecha = date.fromisoformat(fecha_str)
    except (TypeError, ValueError):
        messages.error(request, 'La fecha de pago no es válida.')
        return redirect('creditos_ventas:cuotas_factura', pk=invoice.pk)

    fecha_factura = invoice.invoice_date.date() if hasattr(invoice.invoice_date, 'date') else invoice.invoice_date
    if fecha > timezone.localdate():
        messages.error(request, 'La fecha de pago no puede ser futura.')
        return redirect('creditos_ventas:cuotas_factura', pk=invoice.pk)
    if fecha < fecha_factura:
        messages.error(request, 'La fecha de pago no puede ser anterior a la fecha de la factura.')
        return redirect('creditos_ventas:cuotas_factura', pk=invoice.pk)

    cuotas = list(CuotaVenta.objects.filter(pk__in=cuota_ids, factura=invoice))
    encontrados = {str(cu.pk) for cu in cuotas}
    faltantes = [cid for cid in cuota_ids if cid not in encontrados]
    if faltantes:
        messages.error(
            request,
            f'No se procesó el pago: la(s) cuota(s) con ID {", ".join(faltantes)} '
            f'no pertenece(n) a esta factura.'
        )
        return redirect('creditos_ventas:cuotas_factura', pk=invoice.pk)

    try:
        with transaction.atomic():
            total_pagado = Decimal('0')
            for cuota in cuotas:
                if cuota.estado == 'PAGADA':
                    raise ValueError(f'la cuota {cuota.numero} ya está pagada por completo.')
                valor = cuota.saldo
                PagoCuotaVenta.objects.create(
                    cuota=cuota, fecha=fecha, valor=valor, observacion='Pago en lote',
                )
                recalcular_cuota(cuota)
                total_pagado += valor
            recalcular_factura(invoice)
    except ValueError as e:
        messages.error(request, f'No se procesó el pago en lote: {e}')
        return redirect('creditos_ventas:cuotas_factura', pk=invoice.pk)

    messages.success(
        request,
        f'Se pagaron {len(cuotas)} cuota(s) por un total de ${total_pagado}.'
    )
    return redirect('creditos_ventas:cuotas_factura', pk=invoice.pk)


class HistorialPagosCuotaView(LoginRequiredMixin, ListView):
    """Historial de pagos de UNA cuota."""
    model = PagoCuotaVenta
    template_name = 'creditos_ventas/historial_pagos.html'
    context_object_name = 'pagos'

    def get_queryset(self):
        self.cuota = get_object_or_404(CuotaVenta, pk=self.kwargs['pk'])
        return PagoCuotaVenta.objects.filter(cuota=self.cuota).select_related('cuota').order_by('-fecha', '-id')

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


# === PDF ===

@login_required
def plan_pagos_pdf_view(request, invoice_pk):
    """Genera el PDF del Plan de Pagos / Estado de Cuenta de una factura a crédito."""
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    pdf_bytes = generar_pdf_plan_pagos(invoice)
    return HttpResponse(pdf_bytes, content_type='application/pdf')
