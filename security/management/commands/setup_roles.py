from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


ROLES = {
    # El Administrador recibe TODOS los permisos
    'Administrador': '__all__',

    # El Vendedor gestiona clientes y facturas (y VE productos)
    'Vendedor': [
        'view_customer', 'add_customer', 'change_customer',
        'view_customerprofile', 'add_customerprofile', 'change_customerprofile',
        'view_invoice', 'add_invoice', 'change_invoice',
        'view_invoicedetail', 'add_invoicedetail', 'change_invoicedetail',
        'view_product',
        # Mismo nivel de acceso que ya tiene sobre Factura: gestiona las
        # cuotas y pagos de crédito de sus ventas, pero no las elimina.
        'view_cuotaventa', 'add_cuotaventa', 'change_cuotaventa',
        'view_pagocuotaventa', 'add_pagocuotaventa', 'change_pagocuotaventa',
    ],

    # El Analista de Compras gestiona el catálogo completo
    'Analista de Compras': [
        'view_brand', 'add_brand', 'change_brand', 'delete_brand',
        'view_productgroup', 'add_productgroup', 'change_productgroup', 'delete_productgroup',
        'view_supplier', 'add_supplier', 'change_supplier', 'delete_supplier',
        'view_product', 'add_product', 'change_product', 'delete_product',
        # Mismo nivel de acceso que ya tiene sobre Producto/Proveedor.
        'view_cuotacompra', 'add_cuotacompra', 'change_cuotacompra', 'delete_cuotacompra',
        'view_pagocuotacompra', 'add_pagocuotacompra', 'change_pagocuotacompra', 'delete_pagocuotacompra',
        # Exportar PDF/Excel de todo el catálogo que gestiona.
        'exportar_pdf_brand', 'exportar_excel_brand',
        'exportar_pdf_productgroup', 'exportar_excel_productgroup',
        'exportar_pdf_supplier', 'exportar_excel_supplier',
        'exportar_pdf_product', 'exportar_excel_product',
        # 'imprimir_plan_pagos' existe también en creditos_ventas.CuotaVenta
        # con el mismo codename: se califica con su app para no traerse esa.
        ('creditos_compras', 'imprimir_plan_pagos'),
    ],

    # El Auditor solo consulta: ve y exporta/imprime todo el catálogo,
    # ventas y compras, pero no crea/edita/elimina nada.
    'Auditor': [
        'view_brand', 'view_productgroup', 'view_supplier', 'view_product',
        'view_customer', 'view_customerprofile',
        'view_invoice', 'view_invoicedetail',
        'view_purchase', 'view_purchasedetail', 'view_purchase_report',
        'exportar_pdf_brand', 'exportar_excel_brand',
        'exportar_pdf_productgroup', 'exportar_excel_productgroup',
        'exportar_pdf_supplier', 'exportar_excel_supplier',
        'exportar_pdf_product', 'exportar_excel_product',
        'exportar_pdf_customer', 'exportar_excel_customer',
        'exportar_pdf_invoice', 'exportar_excel_invoice',
        'exportar_pdf_purchase', 'exportar_excel_purchase',
        'imprimir_factura', 'imprimir_orden_compra',
        'view_cuotaventa', 'view_pagocuotaventa',
        'view_cuotacompra', 'view_pagocuotacompra',
        # 'imprimir_plan_pagos' se repite en creditos_ventas y
        # creditos_compras: el Auditor debe ver ambos, así que se listan
        # las dos entradas calificadas explícitamente.
        ('creditos_ventas', 'imprimir_plan_pagos'),
        ('creditos_compras', 'imprimir_plan_pagos'),
    ],

    # El Cajero gestiona clientes y facturas al contado, sin eliminar.
    'Cajero': [
        'view_customer', 'add_customer', 'change_customer',
        'view_customerprofile', 'add_customerprofile', 'change_customerprofile',
        'view_invoice', 'add_invoice',
        'view_invoicedetail', 'add_invoicedetail', 'change_invoicedetail',
        'view_product',
        'exportar_pdf_customer', 'exportar_excel_customer',
        'exportar_pdf_invoice', 'exportar_excel_invoice',
        'imprimir_factura',
        # Cierra facturas CONTADO+PayPal abandonadas en PENDIENTE (B8):
        # el Cajero es quien atiende el mostrador y ve estas facturas
        # colgadas, así que necesita poder liberar el stock reservado.
        'cancelar_invoice_paypal',
    ],

    # El Supervisor de Ventas tiene el mismo alcance que Cajero pero con
    # permiso de eliminar sobre clientes y facturas, y visibilidad de cuotas.
    'Supervisor de Ventas': [
        'view_customer', 'add_customer', 'change_customer', 'delete_customer',
        'view_customerprofile', 'add_customerprofile', 'change_customerprofile', 'delete_customerprofile',
        'view_invoice', 'add_invoice', 'change_invoice', 'delete_invoice',
        'view_invoicedetail', 'add_invoicedetail', 'change_invoicedetail', 'delete_invoicedetail',
        'view_product',
        'exportar_pdf_customer', 'exportar_excel_customer',
        'exportar_pdf_invoice', 'exportar_excel_invoice',
        'imprimir_factura',
        'view_cuotaventa', 'view_pagocuotaventa',
    ],
}


class Command(BaseCommand):
    help = 'Crea los 6 roles del sistema con sus permisos'

    def handle(self, *args, **kwargs):
        for role_name, codenames in ROLES.items():
            # get_or_create: si el rol ya existe NO lo duplica
            group, created = Group.objects.get_or_create(name=role_name)

            if codenames == '__all__':
                perms = Permission.objects.all()
            else:
                # Entradas planas: codename tal cual (puede matchear más de
                # un content_type si el codename se repite entre modelos).
                # Entradas (app_label, codename): califican el content_type
                # para evitar traerse el permiso homónimo de otra app.
                plain = [c for c in codenames if isinstance(c, str)]
                qualified = [c for c in codenames if isinstance(c, tuple)]
                perms = Permission.objects.filter(codename__in=plain)
                for app_label, codename in qualified:
                    perms = perms | Permission.objects.filter(
                        codename=codename, content_type__app_label=app_label
                    )

            # set() reemplaza los permisos del rol por esta lista
            group.permissions.set(perms)

            status = 'creado' if created else 'actualizado'
            self.stdout.write(self.style.SUCCESS(
                f'Rol "{role_name}" {status} con {perms.count()} permisos'
            ))
