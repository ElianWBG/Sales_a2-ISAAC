"""Formato de moneda compartido por correos y mensajes en pantalla.

Mismo formato que ya usaba _money() en billing/invoice_pdf.py y
purchasing/purchase_pdf.py (2 decimales, separador de miles) -- se centraliza
acá para no repetirlo en cada view/email que arma un mensaje con un total.
"""


def money(valor):
    return f'${valor:,.2f}'
