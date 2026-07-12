from django.urls import path
from . import views

app_name = 'creditos_ventas'

urlpatterns = [
    path('factura/<int:pk>/cuotas/', views.CuotaListView.as_view(), name='cuotas_factura'),
    path('pendientes/', views.CuotaPendientesListView.as_view(), name='cuotas_pendientes'),
    path('cuota/<int:pk>/eliminar/', views.CuotaDeleteView.as_view(), name='cuota_delete'),

    path('cuota/<int:cuota_pk>/pagar/', views.registrar_pago, name='registrar_pago'),
    path('factura/<int:invoice_pk>/cuotas/pagar-lote/', views.pagar_cuotas_lote, name='pagar_cuotas_lote'),

    path('cuota/<int:pk>/pagos/', views.HistorialPagosCuotaView.as_view(), name='historial_pagos_cuota'),
    path('factura/<int:pk>/pagos/', views.HistorialPagosFacturaView.as_view(), name='historial_pagos_factura'),

    path('factura/<int:invoice_pk>/plan-pagos/pdf/', views.plan_pagos_pdf_view, name='plan_pagos_pdf'),
]
