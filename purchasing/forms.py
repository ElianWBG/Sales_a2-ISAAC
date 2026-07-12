from django import forms
from django.forms import inlineformset_factory
from .models import Purchase, PurchaseDetail


# ── Cabecera de la compra ──
class PurchaseForm(forms.ModelForm):
    """Formulario para la cabecera de compra."""
    class Meta:
        model = Purchase
        fields = ['supplier', 'document_number']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
        }


# ── Detalle (formset): varias líneas dentro de UNA compra ──
PurchaseDetailFormSet = inlineformset_factory(
    Purchase,          # Modelo padre
    PurchaseDetail,    # Modelo hijo
    fields=['product', 'quantity', 'unit_cost'],
    extra=1,
    can_delete=True,
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
    },
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