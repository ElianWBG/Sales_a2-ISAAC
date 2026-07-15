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
        permissions = [
            ('imprimir_plan_pagos', 'Puede imprimir el plan de pagos'),
        ]

    def __str__(self):
        return f'Cuota {self.numero} - Factura #{self.factura_id}'


class PagoCuotaVenta(models.Model):
    METODO_PAGO_CHOICES = [
        ("EFECTIVO", "Efectivo"),
        ("TRANSFERENCIA", "Transferencia"),
        ("PAYPAL", "PayPal"),
    ]

    PAYPAL_STATUS_CHOICES = [
        ("CREATED", "Creada"),
        ("APPROVED", "Aprobada"),
        ("COMPLETED", "Completada"),
        ("FAILED", "Fallida"),
    ]

    cuota = models.ForeignKey(CuotaVenta, on_delete=models.PROTECT, related_name='pagos')
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True)

    # --- Método de pago de esta cuota ---
    metodo_pago = models.CharField(
        max_length=15,
        choices=METODO_PAGO_CHOICES,
        blank=True,
        null=True,
        verbose_name='Método de pago',
    )

    # --- Datos de la transacción de PayPal (solo se llenan si metodo_pago == 'PAYPAL') ---
    paypal_order_id = models.CharField(max_length=50, blank=True, null=True, verbose_name='ID de orden PayPal')
    paypal_capture_id = models.CharField(max_length=50, blank=True, null=True, verbose_name='ID de captura PayPal')
    paypal_status = models.CharField(
        max_length=15, choices=PAYPAL_STATUS_CHOICES, blank=True, null=True, verbose_name='Estado PayPal'
    )
    paypal_payer_email = models.EmailField(blank=True, null=True, verbose_name='Correo del pagador (PayPal)')

    def __str__(self):
        return f'Pago ${self.valor} - Cuota {self.cuota.numero}'