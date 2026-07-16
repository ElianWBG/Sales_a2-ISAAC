from django import forms
from django.forms import BaseInlineFormSet
from .models import (
    Brand, ProductGroup, Supplier, Product, Customer, Invoice, InvoiceDetail,
    ConfiguracionSistema,
)

_sm_text   = {'class': 'form-control form-control-sm'}
_sm_select = {'class': 'form-select form-select-sm'}
_sm_number = {'class': 'form-control form-control-sm', 'min': '0'}

class ProductSearchForm(forms.Form):
    name = forms.CharField(
        required=False, label='Nombre',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar nombre…'})
    )
    brand = forms.ModelChoiceField(
        queryset=Brand.objects.order_by('name'),
        required=False, label='Marca', empty_label='Todas las marcas',
        widget=forms.Select(attrs=_sm_select)
    )
    group = forms.ModelChoiceField(
        queryset=ProductGroup.objects.order_by('name'),
        required=False, label='Grupo', empty_label='Todos los grupos',
        widget=forms.Select(attrs=_sm_select)
    )
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.order_by('name'),
        required=False, label='Proveedor', empty_label='Todos los proveedores',
        widget=forms.Select(attrs=_sm_select)
    )
    price_min = forms.DecimalField(
        required=False, label='Precio mín',
        widget=forms.NumberInput(attrs={**_sm_number, 'placeholder': 'Mín', 'step': '0.01'})
    )
    price_max = forms.DecimalField(
        required=False, label='Precio máx',
        widget=forms.NumberInput(attrs={**_sm_number, 'placeholder': 'Máx', 'step': '0.01'})
    )
    stock_min = forms.IntegerField(
        required=False, label='Stock mín',
        widget=forms.NumberInput(attrs={**_sm_number, 'placeholder': 'Mín'})
    )
    stock_max = forms.IntegerField(
        required=False, label='Stock máx',
        widget=forms.NumberInput(attrs={**_sm_number, 'placeholder': 'Máx'})
    )

class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'description': forms.Textarea(attrs={'class':'form-control','rows':3}),
            'is_active': forms.CheckboxInput(attrs={'class':'form-check-input'}),
        }



class ProductGroupForm(forms.ModelForm):
    class Meta:
        model = ProductGroup
        fields = ['name', 'is_active']

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_name', 'email', 'phone', 'address', 'is_active']

class ProductForm(forms.ModelForm):
    """
    Formulario completo para crear y editar productos.
    Centraliza widgets, estilos Bootstrap, validaciones y mensajes de error.
    """
    class Meta:
        model = Product
        fields = ['name', 'description', 'brand', 'group', 'suppliers',
                  'unit_price', 'stock', 'image', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Laptop Dell XPS 15',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Descripción detallada del producto…',
            }),
            'brand': forms.Select(attrs={
                'class': 'form-select',
            }),
            'group': forms.Select(attrs={
                'class': 'form-select',
            }),
            'suppliers': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '5',
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
                'placeholder': '0.00',
                'id': 'id_unit_price',
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '1',
                'placeholder': '0',
                'id': 'id_stock',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'id': 'id_image',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch',
            }),
        }
        labels = {
            'name':        'Nombre del producto',
            'description': 'Descripción',
            'brand':       'Marca',
            'group':       'Categoría',
            'suppliers':   'Proveedores',
            'unit_price':  'Precio unitario ($)',
            'stock':       'Stock disponible',
            'image':       'Imagen del producto',
            'is_active':   'Producto activo',
        }
        help_texts = {
            'suppliers':  'Mantén Ctrl para seleccionar varios.',
            'unit_price': 'Debe ser mayor que cero.',
            'stock':      'Cantidad disponible en inventario.',
            'image':      'Formatos: JPG, PNG, WEBP. Máx. 5 MB.',
        }
        error_messages = {
            'name':       {'required': 'El nombre del producto es obligatorio.'},
            'brand':      {'required': 'Selecciona una marca.'},
            'group':      {'required': 'Selecciona una categoría.'},
            'unit_price': {
                'required': 'El precio es obligatorio.',
                'invalid':  'Ingresa un valor numérico válido.',
            },
            'stock': {'required': 'El stock es obligatorio.'},
        }

    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price')
        if price is not None and price <= 0:
            raise forms.ValidationError('El precio unitario debe ser mayor que cero.')
        return price

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock is not None and stock < 0:
            raise forms.ValidationError('El stock no puede ser negativo.')
        return stock

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['dni', 'first_name', 'last_name', 'email', 'phone', 'address', 'is_active']


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionSistema
        fields = ['iva_porcentaje']

    def clean_iva_porcentaje(self):
        # Los MinValueValidator(0)/MaxValueValidator(100) del modelo ya
        # cubren esto vía full_clean(), pero se declara explícito acá
        # también (mismo patrón que ProductForm.clean_unit_price) para que
        # el mensaje de error sea el mismo estilo amigable del resto del
        # formulario, sin depender del texto genérico de los validators.
        iva = self.cleaned_data.get('iva_porcentaje')
        if iva is not None and (iva < 0 or iva > 100):
            raise forms.ValidationError('El IVA debe estar entre 0% y 100%.')
        return iva


class InvoiceForm(forms.ModelForm):
    num_cuotas = forms.IntegerField(
        required=False, min_value=1, label='Número de cuotas mensuales',
        help_text='Solo si el tipo de pago es CRÉDITO.',
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = Invoice
        fields = ['customer', 'tipo_pago', 'metodo_pago']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'tipo_pago': forms.Select(attrs={'class': 'form-select'}),
            'metodo_pago': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned = super().clean()
        tipo_pago = cleaned.get('tipo_pago')
        if tipo_pago == 'CREDITO':
            num = cleaned.get('num_cuotas')
            if not num or num < 1:
                raise forms.ValidationError('Debes indicar el número de cuotas (mínimo 1) para una venta a crédito.')
            # El pago de una factura a crédito se registra por cuota
            # (creditos_ventas.PagoCuotaVenta); acá no aplica.
            cleaned['metodo_pago'] = None
        elif tipo_pago == 'CONTADO' and not cleaned.get('metodo_pago'):
            self.add_error('metodo_pago', 'Selecciona un método de pago para una factura de contado.')
        return cleaned

    def save(self, commit=True):
        invoice = super().save(commit=False)
        if invoice.tipo_pago == 'CREDITO':
            invoice.metodo_pago = None
        if commit:
            invoice.save()
        return invoice


class BaseInvoiceDetailFormSet(BaseInlineFormSet):
    """
    Rechaza la factura COMPLETA si cualquier línea pide más cantidad de
    producto de la disponible en stock (validación de primera línea de
    defensa; la vista además revalida con locking dentro de la transacción,
    ver invoice_create).
    """
    def clean(self):
        super().clean()
        errores = []
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or form.cleaned_data.get('DELETE'):
                continue
            product = form.cleaned_data.get('product')
            quantity = form.cleaned_data.get('quantity')
            if product and quantity:
                if quantity > product.stock:
                    errores.append(
                        f'"{product.name}": pediste {quantity}, pero solo hay {product.stock} en stock.'
                    )
        if errores:
            raise forms.ValidationError(errores)


class InvoiceDetailForm(forms.ModelForm):
    """
    InvoiceDetail.quantity es un IntegerField normal (ni siquiera
    PositiveIntegerField): sin declarar el campo explícito acá, Django no
    rechaza cantidades negativas en el backend -- el 'min': 1 del widget
    es nada más del lado del cliente, y un POST manipulado lo salta sin
    problema. Mismo patrón que PurchaseDetailForm (purchasing/forms.py).
    """
    quantity = forms.IntegerField(
        min_value=1, label='Cantidad',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'value': 1}),
    )

    class Meta:
        model = InvoiceDetail
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
        }

    def clean_unit_price(self):
        # El 'min': 0 del widget es solo HTML -- mismo patrón que
        # ProductForm.clean_unit_price (catálogo) para que un POST
        # manipulado no pueda colar un precio en cero o negativo.
        price = self.cleaned_data.get('unit_price')
        if price is not None and price <= 0:
            raise forms.ValidationError('El precio unitario debe ser mayor que cero.')
        return price


InvoiceDetailFormSet = forms.inlineformset_factory(
    Invoice,
    InvoiceDetail,
    form=InvoiceDetailForm,
    formset=BaseInvoiceDetailFormSet,
    extra=1,
    can_delete=True,
)

# ── Formularios de búsqueda por módulo ────────────────────────────────────────

_ACTIVE_CHOICES = [('', 'Todos'), ('1', 'Activo'), ('0', 'Inactivo')]

class BrandSearchForm(forms.Form):
    name = forms.CharField(
        required=False, label='Nombre',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar nombre…'})
    )
    is_active = forms.ChoiceField(
        choices=_ACTIVE_CHOICES, required=False, label='Estado',
        widget=forms.Select(attrs=_sm_select)
    )

class ProductGroupSearchForm(forms.Form):
    name = forms.CharField(
        required=False, label='Nombre',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar nombre…'})
    )
    is_active = forms.ChoiceField(
        choices=_ACTIVE_CHOICES, required=False, label='Estado',
        widget=forms.Select(attrs=_sm_select)
    )

class SupplierSearchForm(forms.Form):
    name = forms.CharField(
        required=False, label='Nombre',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar nombre…'})
    )
    contact_name = forms.CharField(
        required=False, label='Contacto',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar contacto…'})
    )
    email = forms.CharField(
        required=False, label='Email',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar email…'})
    )
    phone = forms.CharField(
        required=False, label='Teléfono',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar teléfono…'})
    )
    is_active = forms.ChoiceField(
        choices=_ACTIVE_CHOICES, required=False, label='Estado',
        widget=forms.Select(attrs=_sm_select)
    )

class CustomerSearchForm(forms.Form):
    dni = forms.CharField(
        required=False, label='DNI/RUC',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar DNI…'})
    )
    last_name = forms.CharField(
        required=False, label='Apellido',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar apellido…'})
    )
    first_name = forms.CharField(
        required=False, label='Nombre',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar nombre…'})
    )
    email = forms.CharField(
        required=False, label='Email',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar email…'})
    )
    phone = forms.CharField(
        required=False, label='Teléfono',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Buscar teléfono…'})
    )

class InvoiceSearchForm(forms.Form):
    customer = forms.CharField(
        required=False, label='Cliente',
        widget=forms.TextInput(attrs={**_sm_text, 'placeholder': 'Nombre, apellido o DNI…'})
    )
    date_from = forms.DateField(
        required=False, label='Fecha desde',
        widget=forms.DateInput(attrs={**_sm_text, 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False, label='Fecha hasta',
        widget=forms.DateInput(attrs={**_sm_text, 'type': 'date'})
    )
    total_min = forms.DecimalField(
        required=False, label='Total mín',
        widget=forms.NumberInput(attrs={**_sm_number, 'placeholder': 'Mín', 'step': '0.01'})
    )
    total_max = forms.DecimalField(
        required=False, label='Total máx',
        widget=forms.NumberInput(attrs={**_sm_number, 'placeholder': 'Máx', 'step': '0.01'})
    )