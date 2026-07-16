"""
Genera el PDF del Plan de Pagos / Estado de Cuenta de una factura a
crédito. Documento separado de billing/invoice_pdf.py (esa es la factura
fija, con el detalle de productos); este refleja el estado de las cuotas
y pagos AL MOMENTO de generarlo, no un documento fijo.
"""

import io

from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from .models import PagoCuotaVenta


def generar_pdf_plan_pagos(invoice):
    """Devuelve los bytes del PDF del plan de pagos de la factura `invoice`."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f'<b>Plan de Pagos - Factura #{invoice.id}</b>', styles['Title']))
    elements.append(Paragraph(f'Cliente: {invoice.customer.full_name}', styles['Normal']))
    elements.append(Paragraph(f'DNI/RUC: {invoice.customer.dni}', styles['Normal']))
    elements.append(Paragraph(f'Tipo de pago: {invoice.get_tipo_pago_display()}', styles['Normal']))
    elements.append(Paragraph(f'Estado de la factura: {invoice.get_estado_display()}', styles['Normal']))
    elements.append(Paragraph(f'Saldo pendiente actual: ${invoice.saldo}', styles['Normal']))
    elements.append(Spacer(1, 0.6 * cm))

    # ── Tabla de cuotas ──
    elements.append(Paragraph('<b>Cuotas</b>', styles['Heading3']))
    cuota_headers = ['Número', 'Vencimiento', 'Valor', 'Saldo', 'Estado']
    cuota_rows = [cuota_headers]
    for cuota in invoice.cuotas.all().order_by('numero'):
        cuota_rows.append([
            str(cuota.numero),
            cuota.fecha_vencimiento.strftime('%d/%m/%Y'),
            f'${cuota.valor}',
            f'${cuota.saldo}',
            cuota.get_estado_display(),
        ])

    cuota_table = Table(cuota_rows, colWidths=[2.5 * cm, 3.5 * cm, 3 * cm, 3 * cm, 3 * cm])
    cuota_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(cuota_table)
    elements.append(Spacer(1, 0.8 * cm))

    # ── Historial de pagos ──
    elements.append(Paragraph('<b>Historial de Pagos</b>', styles['Heading3']))
    pagos = list(
        PagoCuotaVenta.objects
        .filter(cuota__factura=invoice)
        .select_related('cuota')
        .order_by('fecha')
    )
    pago_headers = ['N° Cuota', 'Fecha', 'Valor pagado', 'Observación']
    pago_rows = [pago_headers]
    if pagos:
        for pago in pagos:
            fecha_str = pago.fecha.strftime('%d/%m/%Y')
            if pago.fecha > pago.cuota.fecha_vencimiento:
                fecha_str += ' (atrasado)'
            pago_rows.append([
                str(pago.cuota.numero),
                fecha_str,
                f'${pago.valor}',
                pago.observacion_display,
            ])
    else:
        pago_rows.append(['Sin pagos registrados.', '', '', ''])

    pago_table = Table(pago_rows, colWidths=[2.5 * cm, 3 * cm, 3.5 * cm, 6 * cm])
    pago_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (2, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(pago_table)
    elements.append(Spacer(1, 1 * cm))

    elements.append(Paragraph(
        f'Documento generado el {timezone.localtime().strftime("%d/%m/%Y a las %H:%M")}. '
        f'Refleja el estado de la factura al momento de imprimirlo, a diferencia de la '
        f'Factura (documento fijo).',
        styles['Normal'],
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
