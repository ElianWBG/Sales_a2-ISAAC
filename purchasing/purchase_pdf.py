"""
Genera el PDF de una compra individual (para imprimir/ver el documento).
Misma estructura visual que billing/invoice_pdf.py (generar_pdf_factura),
adaptada a los campos de Purchase/PurchaseDetail.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


def generar_pdf_compra(purchase):
    """Devuelve los bytes del PDF de la compra `purchase`."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f'<b>Compra #{purchase.id}</b>', styles['Title']))
    elements.append(Paragraph(
        f'Fecha: {purchase.purchase_date.strftime("%d/%m/%Y %H:%M")}', styles['Normal']
    ))
    elements.append(Paragraph(f'Proveedor: {purchase.supplier.name}', styles['Normal']))
    elements.append(Paragraph(f'N° Documento: {purchase.document_number}', styles['Normal']))
    elements.append(Spacer(1, 0.6 * cm))

    headers = ['Producto', 'Cantidad', 'Costo unitario', 'Subtotal']
    rows = [headers]
    for d in purchase.details.all():
        rows.append([d.product.name, str(d.quantity), f'${d.unit_cost}', f'${d.subtotal}'])

    table = Table(rows, colWidths=[7 * cm, 3 * cm, 4 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.6 * cm))

    elements.append(Paragraph(f'Subtotal: ${purchase.subtotal}', styles['Normal']))
    elements.append(Paragraph(f'IVA (15%): ${purchase.tax}', styles['Normal']))
    elements.append(Paragraph(f'<b>Total: ${purchase.total}</b>', styles['Normal']))
    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph(
        f'Generado el {datetime.now().strftime("%d/%m/%Y a las %H:%M")}',
        styles['Normal'],
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
