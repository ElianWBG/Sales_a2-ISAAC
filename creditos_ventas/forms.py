from django import forms
from django.utils import timezone
from .models import PagoCuotaVenta

class PagoCuotaVentaForm(forms.ModelForm):
    """
    Formulario de registro de pago de una cuota. Requiere la cuota como
    parámetro (no del POST) para poder validar contra su saldo ACTUAL.
    """
    class Meta:
        model = PagoCuotaVenta
        fields = ['fecha', 'valor', 'metodo_pago', 'observacion']
        widgets = {
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'metodo_pago': forms.Select(attrs={'class': 'form-select'}),
            'observacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'fecha': 'Fecha de pago',
            'valor': 'Valor pagado',
            'metodo_pago': 'Método de pago',
            'observacion': 'Observación',
        }

    def __init__(self, *args, cuota=None, **kwargs):
        self.cuota = cuota
        super().__init__(*args, **kwargs)
        self.fields['observacion'].required = False
        self.fields['metodo_pago'].required = True

    def clean_metodo_pago(self):
        metodo = self.cleaned_data.get('metodo_pago')
        if not metodo:
            raise forms.ValidationError('Selecciona un método de pago.')
        return metodo

    def clean_valor(self):
        valor = self.cleaned_data.get('valor')
        if valor is None or valor <= 0:
            raise forms.ValidationError('El valor del pago debe ser mayor que cero.')
        if self.cuota is not None and valor > self.cuota.saldo:
            raise forms.ValidationError(
                f'El valor no puede superar el saldo actual de la cuota (${self.cuota.saldo}).'
            )
        return valor

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if fecha:
            if fecha > timezone.localdate():
                raise forms.ValidationError('La fecha del pago no puede ser futura.')
            if self.cuota is not None:
                fecha_factura = self.cuota.factura.invoice_date
                if hasattr(fecha_factura, 'date'):
                    fecha_factura = fecha_factura.date()
                if fecha < fecha_factura:
                    raise forms.ValidationError(
                        'La fecha del pago no puede ser anterior a la fecha de la factura.'
                    )
        return fecha