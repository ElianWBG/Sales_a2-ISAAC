from decimal import Decimal
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q, F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, DeleteView

from billing.models import Invoice
from shared.mixins import ProtectedDeleteMixin, PermissionRequiredMixin, AnyCrudPermissionRequiredMixin
from shared.decorators import permission_required_with_message, any_crud_permission_required
from shared.paypal_client import create_paypal_order, capture_paypal_order, extract_capture_data, PayPalError

from .models import CuotaVenta, PagoCuotaVenta
from .forms import PagoCuotaVentaForm, CuotaPendienteSearchForm
from .services import recalcular_cuota, recalcular_factura
from .plan_pagos_pdf import generar_pdf_plan_pagos


# === CUOTAS ===

class CuotaListView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    """Cuotas de UNA factura específica."""
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_list.html'
    context_object_name = 'cuotas'
    # add/change/delete son decorativos en CuotaVenta y están ocultos en la
    # matriz de permisos (ACTIONS_EXCLUDED_PER_MODEL): add/change porque no
    # hay formulario propio (las cuotas se generan solo en generar_cuotas),
    # delete porque CuotaDeleteView existe pero ningún template la enlaza.
    # Si se dejara el default de los 4 CRUD, un rol que alguna vez tuvo
    # cualquiera de estos tres (ej. viniendo de un rol '__all__') mantendría
    # acceso a "Ver Cuotas" para siempre, sin ningún checkbox con el que
    # quitárselo -- Ver es la única acción real acá.
    crud_actions = ('view',)

    def get_queryset(self):
        self.factura = get_object_or_404(Invoice, pk=self.kwargs['pk'])
        return CuotaVenta.objects.filter(factura=self.factura)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['factura'] = self.factura
        return ctx


class CuotaPendientesListView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    """Todas las cuotas PENDIENTES del sistema, sin importar la factura."""
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_pendientes_list.html'
    context_object_name = 'cuotas'
    crud_actions = ('view',)  # mismo motivo que CuotaListView

    def get_queryset(self):
        qs = (
            CuotaVenta.objects
            .filter(estado='PENDIENTE')
            .select_related('factura', 'factura__customer')
            .order_by('fecha_vencimiento')
        )
        form = CuotaPendienteSearchForm(self.request.GET)
        if form.is_valid():
            if form.cleaned_data.get('cliente'):
                q = form.cleaned_data['cliente']
                qs = qs.filter(
                    Q(factura__customer__first_name__icontains=q) |
                    Q(factura__customer__last_name__icontains=q) |
                    Q(factura__customer__dni__icontains=q)
                )
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
        ctx['search_form'] = CuotaPendienteSearchForm(self.request.GET)
        return ctx


class CuotaDeleteView(ProtectedDeleteMixin, LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """
    Elimina una cuota. PagoCuotaVenta.cuota usa on_delete=PROTECT, así que
    si la cuota ya tiene pagos registrados, ProtectedDeleteMixin lo bloquea
    con un mensaje amigable en vez de un 500.
    """
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_confirm_delete.html'
    protected_message = 'No se puede eliminar la cuota porque tiene pagos registrados.'
    success_message = 'Cuota eliminada correctamente.'
    permission_required = 'creditos_ventas.delete_cuotaventa'
    permission_redirect_url = '/'

    def get_success_url(self):
        return reverse('creditos_ventas:cuotas_factura', kwargs={'pk': self.object.factura_id})


# === PAGOS ===

@login_required
@permission_required_with_message('creditos_ventas.add_pagocuotaventa', redirect_url='/')
def registrar_pago(request, cuota_pk):
    """Registra un pago sobre una cuota y recalcula cuota + factura."""
    cuota = get_object_or_404(CuotaVenta, pk=cuota_pk)

    if cuota.estado == 'PAGADA':
        messages.error(request, 'Esta cuota ya está pagada por completo, no admite más pagos.')
        return redirect('creditos_ventas:cuotas_factura', pk=cuota.factura_id)

    if request.method == 'POST':
        # select_for_update() DENTRO de la transacción, ANTES de armar/validar
        # el form: PagoCuotaVentaForm.clean_valor compara `valor` contra
        # `cuota.saldo`, así que ese saldo tiene que venir de la fila ya
        # bloqueada -- si se bloqueara después de validar, dos pagos
        # concurrentes ya habrían leído el mismo saldo stale y ambos
        # pasarían la validación (mismo patrón que select_for_update()
        # sobre Product en invoice_create).
        with transaction.atomic():
            cuota_locked = CuotaVenta.objects.select_for_update().get(pk=cuota.pk)

            if cuota_locked.estado == 'PAGADA':
                messages.error(request, 'Esta cuota ya está pagada por completo, no admite más pagos.')
                return redirect('creditos_ventas:cuotas_factura', pk=cuota_locked.factura_id)

            form = PagoCuotaVentaForm(request.POST, cuota=cuota_locked)
            if form.is_valid():
                pago = form.save(commit=False)
                pago.cuota = cuota_locked

                if pago.metodo_pago == 'PAYPAL':
                    # Igual que con la factura de contado: NO se confirma el
                    # pago (ni se recalcula saldo) todavía. Se guarda el
                    # registro para tener un pk que usar en los endpoints AJAX
                    # de create-order/capture-order, y recién se recalcula
                    # cuando PayPal confirme la captura.
                    pago.save()
                    return redirect('creditos_ventas:pago_paypal_checkout', pago_pk=pago.pk)

                pago.save()
                recalcular_cuota(cuota_locked)
                recalcular_factura(cuota_locked.factura)
                messages.success(
                    request,
                    f'Pago de ${pago.valor} registrado en la cuota {cuota_locked.numero} de la factura #{cuota_locked.factura_id}.'
                )
                return redirect('creditos_ventas:cuotas_factura', pk=cuota_locked.factura_id)
    else:
        form = PagoCuotaVentaForm(cuota=cuota, initial={'fecha': timezone.localdate()})

    return render(request, 'creditos_ventas/registrar_pago.html', {'form': form, 'cuota': cuota})

@login_required
@permission_required_with_message('creditos_ventas.add_pagocuotaventa', redirect_url='/')
def pago_paypal_checkout(request, pago_pk):
    """Pantalla con el botón de PayPal para terminar de pagar una cuota."""
    pago = get_object_or_404(PagoCuotaVenta, pk=pago_pk)
    if pago.metodo_pago != 'PAYPAL' or pago.paypal_status == 'COMPLETED':
        messages.info(request, 'Este pago no admite (o ya no necesita) confirmación con PayPal.')
        return redirect('creditos_ventas:cuotas_factura', pk=pago.cuota.factura_id)
    return render(request, 'creditos_ventas/pago_paypal_checkout.html', {
        'pago': pago,
        'cuota': pago.cuota,
        'paypal_client_id': settings.PAYPAL_CLIENT_ID,
    })


@login_required
@permission_required_with_message('creditos_ventas.add_pagocuotaventa', redirect_url='/')
def pago_paypal_create_order(request, pago_pk):
    """Endpoint AJAX: pide a PayPal el order_id antes de abrir el checkout."""
    pago = get_object_or_404(PagoCuotaVenta, pk=pago_pk)
    if pago.metodo_pago != 'PAYPAL' or pago.paypal_status == 'COMPLETED':
        return JsonResponse({'error': 'Este pago no admite PayPal en este momento.'}, status=400)
    try:
        order = create_paypal_order(
            pago.valor,
            description=f'Cuota {pago.cuota.numero} - Factura #{pago.cuota.factura_id}'
        )
    except PayPalError as e:
        return JsonResponse({'error': str(e)}, status=502)

    pago.paypal_order_id = order['id']
    pago.paypal_status = 'CREATED'
    pago.save(update_fields=['paypal_order_id', 'paypal_status'])
    return JsonResponse({'id': order['id']})


@login_required
@permission_required_with_message('creditos_ventas.add_pagocuotaventa', redirect_url='/')
def pago_paypal_capture_order(request, pago_pk):
    """Endpoint AJAX: confirma la captura y recién ahí recalcula cuota/factura."""
    pago = get_object_or_404(PagoCuotaVenta, pk=pago_pk)
    if not pago.paypal_order_id:
        return JsonResponse({'error': 'Este pago no tiene una orden de PayPal creada.'}, status=400)

    try:
        capture = capture_paypal_order(pago.paypal_order_id)
    except PayPalError as e:
        return JsonResponse({'error': str(e)}, status=502)

    data = extract_capture_data(capture)
    pago.paypal_capture_id = data['capture_id']
    pago.paypal_status = data['status']
    pago.paypal_payer_email = data['payer_email']

    if data['status'] != 'COMPLETED':
        pago.save()
        return JsonResponse(
            {'error': f'PayPal no completó el pago (estado: {data["status"]}).'}, status=400
        )

    with transaction.atomic():
        pago.save()
        recalcular_cuota(pago.cuota)
        recalcular_factura(pago.cuota.factura)

    return JsonResponse({'status': 'COMPLETED'})

@login_required
@permission_required_with_message('creditos_ventas.add_pagocuotaventa', redirect_url='/')
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

    # .date() crudo trunca en UTC, no en hora local (ver mismo fix en
    # creditos_ventas/services.py y forms.py).
    if hasattr(invoice.invoice_date, 'tzinfo') and invoice.invoice_date.tzinfo is not None:
        fecha_factura = timezone.localtime(invoice.invoice_date).date()
    elif hasattr(invoice.invoice_date, 'date'):
        fecha_factura = invoice.invoice_date.date()
    else:
        fecha_factura = invoice.invoice_date
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
            # select_for_update() DENTRO de la transacción, releyendo las
            # cuotas en vez de reusar la lista de arriba (fetched antes del
            # atomic, sin lock): acá se lee `cuota.saldo` directo para
            # pagarlo completo, así que si esa lectura es stale, dos pagos
            # en lote concurrentes sobre la misma cuota podrían generar dos
            # PagoCuotaVenta por el total (mismo problema que en
            # registrar_pago, incluso sin pasar por el form).
            cuotas_locked = list(
                CuotaVenta.objects.select_for_update().filter(pk__in=encontrados)
            )
            total_pagado = Decimal('0')
            for cuota in cuotas_locked:
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


class HistorialPagosCuotaView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    """Historial de pagos de UNA cuota."""
    model = PagoCuotaVenta
    template_name = 'creditos_ventas/historial_pagos.html'
    context_object_name = 'pagos'
    # "Ver" controla el acceso al Historial de forma independiente de
    # "Crear" (que gatea registrar_pago aparte, con su propio permission_
    # required_with_message) -- antes esto era ('view', 'add') por OR con
    # la acción real de la fila, pero eso significaba que alguien sin "Ver"
    # podía igual entrar al Historial con solo "Crear" marcado. change/
    # delete siguen sin efecto (no hay vista para editar/eliminar un pago).
    crud_actions = ('view',)

    def get_queryset(self):
        self.cuota = get_object_or_404(CuotaVenta, pk=self.kwargs['pk'])
        return PagoCuotaVenta.objects.filter(cuota=self.cuota).select_related('cuota').order_by('-fecha', '-id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cuota'] = self.cuota
        ctx['factura'] = self.cuota.factura
        return ctx


class HistorialPagosFacturaView(LoginRequiredMixin, AnyCrudPermissionRequiredMixin, ListView):
    """Historial de pagos de TODAS las cuotas de una factura."""
    model = PagoCuotaVenta
    template_name = 'creditos_ventas/historial_pagos.html'
    context_object_name = 'pagos'
    crud_actions = ('view',)  # mismo motivo que HistorialPagosCuotaView

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
@permission_required_with_message('creditos_ventas.imprimir_plan_pagos', redirect_url='/')
def plan_pagos_pdf_view(request, invoice_pk):
    """Genera el PDF del Plan de Pagos / Estado de Cuenta de una factura a crédito."""
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    pdf_bytes = generar_pdf_plan_pagos(invoice)
    return HttpResponse(pdf_bytes, content_type='application/pdf')
