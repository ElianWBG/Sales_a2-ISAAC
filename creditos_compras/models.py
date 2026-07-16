from decimal import Decimal

from django.db import models
from purchasing.models import Purchase


class CuotaCompra(models.Model):
    compra = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name='cuotas')
    numero = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=[("PENDIENTE", "PENDIENTE"), ("PAGADA", "PAGADA")], default="PENDIENTE")

    class Meta:
        ordering = ['compra', 'numero']
        constraints = [
            models.UniqueConstraint(fields=['compra', 'numero'], name='unique_cuota_numero_por_compra')
        ]
        permissions = [
            ('imprimir_plan_pagos', 'Puede imprimir el plan de pagos'),
        ]

    def __str__(self):
        return f'Cuota {self.numero} - Compra #{self.compra_id}'

    @property
    def estado_display(self):
        """
        Estado VISUAL para el badge de la UI -- no reemplaza `estado`, que
        sigue siendo PENDIENTE/PAGADA en la BD y es lo único de lo que
        depende la lógica real (checkbox de pago en lote, registrar_pago,
        cuota_pendientes_list, permisos, etc.). "PARCIAL" es solo una forma
        más clara de mostrar una cuota PENDIENTE que ya tiene algo abonado
        (0 < saldo < valor).
        """
        if self.estado == 'PAGADA':
            return 'PAGADA'
        if self.saldo < self.valor:
            return 'PARCIAL'
        return 'PENDIENTE'


class PagoCuotaCompra(models.Model):
    cuota = models.ForeignKey(CuotaCompra, on_delete=models.PROTECT, related_name='pagos')
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True)

    def __str__(self):
        return f'Pago ${self.valor} - Cuota {self.cuota.numero}'

    @property
    def observacion_display(self):
        """
        Texto para el historial web y los PDF de Plan de Pagos cuando el
        usuario no escribió nada en observación: "Pago total" si este pago,
        sumado a los anteriores de la misma cuota (por fecha, y por orden
        de creación en empates el mismo día), llega a cubrir el valor
        completo de la cuota; "Pago parcial" si todavía queda saldo
        pendiente después de este pago. Si el usuario SÍ escribió algo, se
        respeta tal cual -- nunca se sobreescribe una observación real.
        Fuente única: todos los lugares que muestran esta columna llaman a
        esta property en vez de repetir el cálculo cada uno por su cuenta.
        """
        if self.observacion:
            return self.observacion
        pagos_hasta_este = self.cuota.pagos.filter(
            models.Q(fecha__lt=self.fecha) | models.Q(fecha=self.fecha, pk__lte=self.pk)
        )
        total_pagado = pagos_hasta_este.aggregate(total=models.Sum('valor'))['total'] or Decimal('0')
        return 'Pago total' if total_pagado >= self.cuota.valor else 'Pago parcial'
