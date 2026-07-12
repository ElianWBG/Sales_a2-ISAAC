from django.db import models
from billing.models import Invoice


class CuotaVenta(models.Model):
    factura = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='cuotas')
    numero = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=[("PENDIENTE", "PENDIENTE"), ("PAGADA", "PAGADA")], default="PENDIENTE")

    class Meta:
        ordering = ['factura', 'numero']
        constraints = [
            models.UniqueConstraint(fields=['factura', 'numero'], name='unique_cuota_numero_por_factura')
        ]

    def __str__(self):
        return f'Cuota {self.numero} - Factura #{self.factura_id}'


class PagoCuotaVenta(models.Model):
    cuota = models.ForeignKey(CuotaVenta, on_delete=models.PROTECT, related_name='pagos')
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True)

    def __str__(self):
        return f'Pago ${self.valor} - Cuota {self.cuota.numero}'
