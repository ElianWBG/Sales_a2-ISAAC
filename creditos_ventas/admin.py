from django.contrib import admin
from .models import CuotaVenta, PagoCuotaVenta


@admin.register(CuotaVenta)
class CuotaVentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'factura', 'numero', 'fecha_vencimiento', 'valor', 'saldo', 'estado')
    list_filter = ('estado',)
    search_fields = ('factura__id',)


@admin.register(PagoCuotaVenta)
class PagoCuotaVentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cuota', 'fecha', 'valor', 'observacion')
