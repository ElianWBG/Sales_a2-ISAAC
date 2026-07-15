from decimal import Decimal, ROUND_HALF_UP
from datetime import date
import calendar
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import CuotaCompra


def _sumar_meses(fecha, n):
    """Suma n meses a una fecha, ajustando el día si el mes destino es más corto."""
    mes_total = fecha.month - 1 + n
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


@transaction.atomic
def generar_cuotas(purchase, num_cuotas):
    """Genera cuotas mensuales que suman EXACTO purchase.total (el redondeo se absorbe en la última)."""
    total = purchase.total
    valor_base = (total / num_cuotas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    valor_ultima = total - (valor_base * (num_cuotas - 1))
    # .date() crudo trunca en UTC, no en la hora local del negocio (Ecuador,
    # UTC-5): una compra creada a las 20:00 hora local puede quedar
    # guardada como 01:00 UTC del día SIGUIENTE, corriendo un día todos los
    # vencimientos de las cuotas si no se convierte antes de truncar.
    if hasattr(purchase.purchase_date, 'tzinfo') and purchase.purchase_date.tzinfo is not None:
        fecha_base = timezone.localtime(purchase.purchase_date).date()
    elif hasattr(purchase.purchase_date, 'date'):
        fecha_base = purchase.purchase_date.date()
    else:
        fecha_base = purchase.purchase_date

    cuotas = []
    for i in range(1, num_cuotas + 1):
        valor = valor_base if i < num_cuotas else valor_ultima
        cuotas.append(CuotaCompra(
            compra=purchase, numero=i,
            fecha_vencimiento=_sumar_meses(fecha_base, i),
            valor=valor, saldo=valor, estado='PENDIENTE',
        ))
    CuotaCompra.objects.bulk_create(cuotas)


def recalcular_cuota(cuota):
    """Recalcula desde cero sumando TODOS los pagos vigentes (no resta incremental, evita drift)."""
    total_pagado = cuota.pagos.aggregate(s=Sum('valor'))['s'] or Decimal('0')
    cuota.saldo = cuota.valor - total_pagado
    cuota.estado = 'PAGADA' if cuota.saldo <= 0 else 'PENDIENTE'
    cuota.save(update_fields=['saldo', 'estado'])


def recalcular_compra(purchase):
    saldo_total = purchase.cuotas.aggregate(s=Sum('saldo'))['s'] or Decimal('0')
    purchase.saldo = saldo_total
    purchase.estado = 'PAGADA' if saldo_total <= 0 else 'PENDIENTE'
    purchase.save(update_fields=['saldo', 'estado'])
