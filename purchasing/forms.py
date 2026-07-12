from django import forms
from django.forms import inlineformset_factory
from .models import Purchase, PurchaseDetail


# ── Cabecera de la compra ──
class PurchaseForm(forms.ModelForm):
    """Formulario para la cabecera de compra."""
    num_cuotas = forms.IntegerField(
        required=False, min_value=1, label='Número de cuotas mensuales',
        help_text='Solo si el tipo de pago es CRÉDITO.',
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = Purchase
        fields = ['supplier', 'document_number', 'tipo_pago']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_pago': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('tipo_pago') == 'CREDITO':
            num = cleaned.get('num_cuotas')
            if not num or num < 1:
                raise forms.ValidationError('Debes indicar el número de cuotas (mínimo 1) para una compra a crédito.')
        return cleaned


# ── Detalle (formset): varias líneas dentro de UNA compra ──
class PurchaseDetailForm(forms.ModelForm):
    """
    PurchaseDetail.quantity es PositiveIntegerField, que en Django solo
    rechaza negativos (permite 0). El widget con 'min': 1 es nada más
    del lado del cliente. Declaramos el campo explícito con min_value=1
    para que también se valide en el backend.
    """
    quantity = forms.IntegerField(
        min_value=1, label='Cantidad',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
    )

    class Meta:
        model = PurchaseDetail
        fields = ['product', 'quantity', 'unit_cost']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
        }


PurchaseDetailFormSet = inlineformset_factory(
    Purchase,          # Modelo padre
    PurchaseDetail,    # Modelo hijo
    form=PurchaseDetailForm,
    extra=1,
    can_delete=True,
)


# ── Buscador (filtros de la lista) ──
class PurchaseSearchForm(forms.Form):
    supplier = forms.CharField(
        required=False, label='Proveedor',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm',
                                      'placeholder': 'Nombre del proveedor…'})
    )
    document_number = forms.CharField(
        required=False, label='N° Documento',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm',
                                      'placeholder': 'N° factura…'})
    )
    date_from = forms.DateField(
        required=False, label='Desde',
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False, label='Hasta',
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )