from django import forms
from django.utils import timezone
from .models import PagoCuotaCompra


class PagoCuotaCompraForm(forms.ModelForm):
    """
    Formulario de registro de pago de una cuota de compra. Requiere la
    cuota como parámetro (no del POST) para poder validar contra su
    saldo ACTUAL.
    """
    class Meta:
        model = PagoCuotaCompra
        fields = ['fecha', 'valor', 'observacion']
        widgets = {
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'observacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'fecha': 'Fecha de pago',
            'valor': 'Valor pagado',
            'observacion': 'Observación',
        }

    def __init__(self, *args, cuota=None, **kwargs):
        self.cuota = cuota
        super().__init__(*args, **kwargs)
        self.fields['observacion'].required = False

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
                fecha_compra = self.cuota.compra.purchase_date
                # .date() crudo trunca en UTC, no en hora local (Ecuador,
                # UTC-5): sin convertir, una compra creada de noche queda
                # con fecha del día siguiente y bloquea pagos válidos del
                # mismo día.
                if hasattr(fecha_compra, 'tzinfo') and fecha_compra.tzinfo is not None:
                    fecha_compra = timezone.localtime(fecha_compra).date()
                elif hasattr(fecha_compra, 'date'):
                    fecha_compra = fecha_compra.date()
                if fecha < fecha_compra:
                    raise forms.ValidationError(
                        'La fecha del pago no puede ser anterior a la fecha de la compra.'
                    )
        return fecha


# ── Buscador (filtro de Cuotas Pendientes) ──
class CuotaCompraPendienteSearchForm(forms.Form):
    ESTADO_CHOICES = [
        ('', 'Todos'),
        ('PENDIENTE', 'Sin abonar'),
        ('PARCIAL', 'Con abono parcial'),
    ]
    proveedor = forms.CharField(
        required=False, label='Proveedor',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Nombre del proveedor…'})
    )
    fecha_desde = forms.DateField(
        required=False, label='Vence desde',
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )
    fecha_hasta = forms.DateField(
        required=False, label='Vence hasta',
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )
    estado = forms.ChoiceField(
        required=False, label='Estado', choices=ESTADO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
