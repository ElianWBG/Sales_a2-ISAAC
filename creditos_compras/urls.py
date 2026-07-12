from django.urls import path
from . import views

app_name = 'creditos_compras'

urlpatterns = [
    path('compra/<int:pk>/cuotas/', views.CuotaListView.as_view(), name='cuotas_compra'),
    path('pendientes/', views.CuotaPendientesListView.as_view(), name='cuotas_pendientes'),
    path('cuota/<int:pk>/eliminar/', views.CuotaDeleteView.as_view(), name='cuota_delete'),

    path('cuota/<int:cuota_pk>/pagar/', views.registrar_pago, name='registrar_pago'),
    path('compra/<int:purchase_pk>/cuotas/pagar-lote/', views.pagar_cuotas_lote, name='pagar_cuotas_lote'),

    path('cuota/<int:pk>/pagos/', views.HistorialPagosCuotaView.as_view(), name='historial_pagos_cuota'),
    path('compra/<int:pk>/pagos/', views.HistorialPagosCompraView.as_view(), name='historial_pagos_compra'),

    path('compra/<int:purchase_pk>/plan-pagos/pdf/', views.plan_pagos_pdf_view, name='plan_pagos_pdf'),
]
