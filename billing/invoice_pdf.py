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
    from .models import ConfiguracionSistema
    config = ConfiguracionSistema.get_activa()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    negocio_style = ParagraphStyle('Negocio', parent=styles['Normal'], fontSize=18, leading=22, fontName='Helvetica-Bold', textColor=AZUL, spaceAfter=4)
    tributario_style = ParagraphStyle('Tributario', parent=styles['Normal'], fontSize=9, leading=13, textColor=GRIS_TEXTO)
    titulo_doc_style = ParagraphStyle('TituloDoc', parent=styles['Normal'], fontSize=22, fontName='Helvetica-BoldOblique', alignment=TA_RIGHT, textColor=colors.HexColor('#212529'))
    label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', textColor=AZUL, spaceAfter=4)
    normal_style = ParagraphStyle('NormalDoc', parent=styles['Normal'], fontSize=10, leading=14)
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER)
    footer_nota_style = ParagraphStyle('FooterNota', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, textColor=GRIS_TEXTO, spaceBefore=4)
    footer_gen_style = ParagraphStyle('FooterGen', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=GRIS_TEXTO, spaceBefore=10)

    elements = []

    # --- Encabezado: negocio + datos tributarios a la izquierda, título del
    # documento a la derecha. Los datos tributarios vienen de
    # ConfiguracionSistema (editables desde Configuración del Sistema, ya no
    # son constantes fijas en settings.py) y son todos opcionales -- si no
    # están configurados se omite la línea en vez de imprimir un dato
    # inventado. El título usa nombre_comercial si está configurado, para no
    # dejar "Sistema de Ventas" pisando el nombre real del negocio.
    titulo_negocio = config.nombre_comercial or 'Sistema de Ventas'
    establecimiento = (
        f'Estab.: {config.codigo_establecimiento}  Pto. Emisión: {config.punto_emision}'
        if config.codigo_establecimiento and config.punto_emision else None
    )
    tributarios = [
        linea for linea in (
            f'RUC: {config.ruc}' if config.ruc else None,
            f'Razón Social: {config.razon_social}' if config.razon_social and config.razon_social != titulo_negocio else None,
            config.direccion_establecimiento_efectiva or None,
            f'Tel: {config.telefono}' if config.telefono else None,
            establecimiento,
        ) if linea
    ]
    negocio_col = [Paragraph(titulo_negocio, negocio_style)]
    if tributarios:
        negocio_col.append(Paragraph('<br/>'.join(tributarios), tributario_style))

    encabezado = Table(
        [[negocio_col, Paragraph('FACTURA', titulo_doc_style)]],
        colWidths=[9 * cm, 9 * cm],
    )
    encabezado.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, AZUL),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(encabezado)
    elements.append(Spacer(1, 0.6 * cm))

    # --- Datos del cliente y de la factura, en dos recuadros separados ---
    if invoice.tipo_pago == 'CREDITO':
        cuotas_count = invoice.cuotas.count()
        forma_pago = f'CRÉDITO ({cuotas_count} cuota{"s" if cuotas_count != 1 else ""})'
    else:
        metodo = f' - {invoice.get_metodo_pago_display()}' if invoice.metodo_pago else ''
        forma_pago = f'{invoice.get_tipo_pago_display()}{metodo}'

    cliente_lineas = [invoice.customer.full_name, f'DNI/RUC: {invoice.customer.dni}']
    if invoice.customer.phone:
        cliente_lineas.append(f'Tel: {invoice.customer.phone}')
    if invoice.customer.email:
        cliente_lineas.append(invoice.customer.email)

    recuadro_cliente = [
        Paragraph('FACTURAR A', label_style),
        *[Paragraph(l, normal_style) for l in cliente_lineas],
    ]
    recuadro_factura = [
        Paragraph('DATOS DE LA FACTURA', label_style),
        Paragraph(f'<b>N°:</b> {invoice.id}', normal_style),
        Paragraph(f'<b>Fecha:</b> {invoice.invoice_date.strftime("%d/%m/%Y %H:%M")}', normal_style),
        Paragraph(f'<b>Forma de pago:</b> {forma_pago}', normal_style),
    ]

    # Columna angosta sin fondo entre ambos recuadros para que no queden
    # pegados uno al otro (Table no tiene un "gap" nativo entre celdas).
    bloque_datos = Table(
        [[recuadro_cliente, '', recuadro_factura]],
        colWidths=[8.7 * cm, 0.6 * cm, 8.7 * cm],
    )
    bloque_datos.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, 0), GRIS_FONDO),
        ('BACKGROUND', (2, 0), (2, 0), GRIS_FONDO),
        ('BOX', (0, 0), (0, 0), 1, GRIS_BORDE),
        ('BOX', (2, 0), (2, 0), 1, GRIS_BORDE),
        ('LEFTPADDING', (0, 0), (0, 0), 10),
        ('RIGHTPADDING', (0, 0), (0, 0), 10),
        ('LEFTPADDING', (2, 0), (2, 0), 10),
        ('RIGHTPADDING', (2, 0), (2, 0), 10),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
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
