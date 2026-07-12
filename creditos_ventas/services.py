from decimal import Decimal, ROUND_HALF_UP
from datetime import date
import calendar
from django.db import transaction
from django.db.models import Sum
from .models import CuotaVenta


def _sumar_meses(fecha, n):
    """Suma n meses a una fecha, ajustando el día si el mes destino es más corto."""
    mes_total = fecha.month - 1 + n
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


@transaction.atomic
def generar_cuotas(invoice, num_cuotas):
    """Genera cuotas mensuales que suman EXACTO invoice.total (el redondeo se absorbe en la última)."""
    total = invoice.total
    valor_base = (total / num_cuotas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    valor_ultima = total - (valor_base * (num_cuotas - 1))
    fecha_base = invoice.invoice_date.date() if hasattr(invoice.invoice_date, 'date') else invoice.invoice_date

    cuotas = []
    for i in range(1, num_cuotas + 1):
        valor = valor_base if i < num_cuotas else valor_ultima
        cuotas.append(CuotaVenta(
            factura=invoice, numero=i,
            fecha_vencimiento=_sumar_meses(fecha_base, i),
            valor=valor, saldo=valor, estado='PENDIENTE',
        ))
    CuotaVenta.objects.bulk_create(cuotas)


def recalcular_cuota(cuota):
    """Recalcula desde cero sumando TODOS los pagos vigentes (no resta incremental, evita drift)."""
    total_pagado = cuota.pagos.aggregate(s=Sum('valor'))['s'] or Decimal('0')
    cuota.saldo = cuota.valor - total_pagado
    cuota.estado = 'PAGADA' if cuota.saldo <= 0 else 'PENDIENTE'
    cuota.save(update_fields=['saldo', 'estado'])


def recalcular_factura(invoice):
    saldo_total = invoice.cuotas.aggregate(s=Sum('saldo'))['s'] or Decimal('0')
    invoice.saldo = saldo_total
    invoice.estado = 'PAGADA' if saldo_total <= 0 else 'PENDIENTE'
    invoice.save(update_fields=['saldo', 'estado'])
