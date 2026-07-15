"""
Genera el PDF de una factura individual (para adjuntar en el correo al
cliente). Es distinto al ExportMixin de mixins.py: ese exporta LISTADOS
completos con columnas configurables; esto genera el documento de UNA
sola factura, con su detalle de líneas.
"""

import io

from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

AZUL = colors.HexColor('#1a56db')
GRIS_TEXTO = colors.HexColor('#495057')
GRIS_BORDE = colors.HexColor('#dee2e6')
GRIS_FONDO = colors.HexColor('#f8f9fa')


def _money(valor):
    return f'${valor:,.2f}'


def generar_pdf_factura(invoice):
    """Devuelve los bytes del PDF de la factura `invoice`."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    negocio_style = ParagraphStyle('Negocio', parent=styles['Normal'], fontSize=18, fontName='Helvetica-Bold', textColor=AZUL)
    titulo_doc_style = ParagraphStyle('TituloDoc', parent=styles['Normal'], fontSize=22, fontName='Helvetica-BoldOblique', alignment=TA_RIGHT, textColor=colors.HexColor('#212529'))
    label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', textColor=GRIS_TEXTO)
    normal_style = ParagraphStyle('NormalDoc', parent=styles['Normal'], fontSize=10, leading=14)
    datos_der_style = ParagraphStyle('DatosDer', parent=normal_style, alignment=TA_RIGHT)
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER)
    footer_nota_style = ParagraphStyle('FooterNota', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, textColor=GRIS_TEXTO, spaceBefore=4)
    footer_gen_style = ParagraphStyle('FooterGen', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=GRIS_TEXTO, spaceBefore=10)

    elements = []

    # --- Encabezado: negocio a la izquierda, título del documento a la derecha ---
    encabezado = Table(
        [[Paragraph('Sistema de Ventas', negocio_style), Paragraph('FACTURA', titulo_doc_style)]],
        colWidths=[9 * cm, 9 * cm],
    )
    encabezado.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, AZUL),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(encabezado)
    elements.append(Spacer(1, 0.6 * cm))

    # --- Bloque de datos: cliente a la izquierda, fecha/factura/forma de pago a la derecha ---
    if invoice.tipo_pago == 'CREDITO':
        cuotas_count = invoice.cuotas.count()
        forma_pago = f'CRÉDITO ({cuotas_count} cuota{"s" if cuotas_count != 1 else ""})'
    else:
        metodo = f' - {invoice.get_metodo_pago_display()}' if invoice.metodo_pago else ''
        forma_pago = f'{invoice.get_tipo_pago_display()}{metodo}'

    datos_izq = [
        Paragraph('Facturar a:', label_style),
        Paragraph(invoice.customer.full_name, normal_style),
        Paragraph(f'DNI/RUC: {invoice.customer.dni}', normal_style),
    ]
    datos_der = [
        Paragraph(f'<b>FECHA:</b> {invoice.invoice_date.strftime("%d/%m/%Y %H:%M")}', datos_der_style),
        Paragraph(f'<b>FACTURA N°:</b> {invoice.id}', datos_der_style),
        Paragraph(f'<b>FORMA DE PAGO:</b> {forma_pago}', datos_der_style),
    ]
    bloque_datos = Table([[datos_izq, datos_der]], colWidths=[9 * cm, 9 * cm])
    bloque_datos.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(bloque_datos)
    elements.append(Spacer(1, 0.8 * cm))

    # --- Tabla de productos ---
    headers = ['PRODUCTO', 'CANTIDAD', 'PRECIO UNITARIO', 'SUBTOTAL']
    rows = [headers]
    for d in invoice.details.all():
        rows.append([d.product.name, str(d.quantity), _money(d.unit_price), _money(d.subtotal)])

    table = Table(rows, colWidths=[7 * cm, 3 * cm, 4 * cm, 4 * cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRIS_FONDO]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.6 * cm))

    # --- Totales, alineados a la derecha, con recuadro para el TOTAL ---
    totales_rows = [
        ['Subtotal', _money(invoice.subtotal)],
        ['IVA (15%)', _money(invoice.tax)],
        ['TOTAL', _money(invoice.total)],
    ]
    totales = Table(totales_rows, colWidths=[4 * cm, 4 * cm])
    totales.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, 2), (-1, 2), 1, AZUL),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (-1, 2), 12),
        ('TEXTCOLOR', (0, 2), (-1, 2), AZUL),
        ('BACKGROUND', (0, 2), (-1, 2), GRIS_FONDO),
        ('BOX', (0, 2), (-1, 2), 1, AZUL),
        ('TOPPADDING', (0, 2), (-1, 2), 6),
        ('BOTTOMPADDING', (0, 2), (-1, 2), 6),
    ]))
    contenedor_totales = Table([['', totales]], colWidths=[10 * cm, 8 * cm])
    contenedor_totales.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    elements.append(contenedor_totales)
    elements.append(Spacer(1, 1.2 * cm))

    # --- Pie de página ---
    elements.append(Paragraph('¡Gracias por su compra!', footer_style))
    if invoice.tipo_pago == 'CREDITO':
        elements.append(Paragraph(
            'Esta venta es a crédito. Consulta tu plan de pagos para ver el detalle de tus cuotas.',
            footer_nota_style,
        ))
    elements.append(Paragraph(
        f'Generado el {timezone.localtime().strftime("%d/%m/%Y a las %H:%M")}',
        footer_gen_style,
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
