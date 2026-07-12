from django.db import models
from shared.validators import validate_cedula_ec


class Brand(models.Model):
    """Marcas de productos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre de marca')
    description = models.TextField(blank=True, null=True , verbose_name='Descripción')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'
        ordering = ['name']
    def __str__(self): return self.name

class ProductGroup(models.Model):
    """Grupos/categorías de productos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre del grupo')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Product Group'
        verbose_name_plural = 'Product Groups'
        ordering = ['name']
    def __str__(self): return self.name

class Supplier(models.Model):
    """Proveedores. M2M con Product."""
    name = models.CharField(max_length=200, verbose_name='Nombre de la compañia')
    contact_name = models.CharField(max_length=200, blank=True, null=True, verbose_name='Nombre de contacto')
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Teléfono')
    address = models.TextField(blank=True, null=True, verbose_name='Dirección')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['name']
    def __str__(self): return self.name

class Product(models.Model):
    """Productos. FK a Brand/Group, M2M a Supplier."""
    name = models.CharField(max_length=200, verbose_name='Nombre del producto')
    description = models.TextField(blank=True, null=True, verbose_name='Descripción')
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='products', verbose_name='Marca')
    group = models.ForeignKey(ProductGroup, on_delete=models.PROTECT, related_name='products', verbose_name='Grupo')
    suppliers = models.ManyToManyField(Supplier, related_name='products', blank=True, verbose_name='Proveedor')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Precio unitario')
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name='Imagen')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']
    def __str__(self): return f'{self.name} ({self.brand.name})'
    @property
    def balance(self):
        from decimal import Decimal, ROUND_HALF_UP
        return (self.unit_price * self.stock).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

class Customer(models.Model):
    """Clientes. OneToOne con CustomerProfile."""
    dni = models.CharField(max_length=13, unique=True, verbose_name='DNI/RUC', validators=[validate_cedula_ec])
    first_name = models.CharField(max_length=100, verbose_name='Nombre')
    last_name = models.CharField(max_length=100, verbose_name='Apellido')
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Teléfono')
    address = models.TextField(blank=True, null=True, verbose_name='Dirección')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['last_name', 'first_name']
    def __str__(self): return f'{self.last_name}, {self.first_name}'
    @property
    def full_name(self): return f'{self.first_name} {self.last_name}'

class CustomerProfile(models.Model):
    """Perfil extendido. OneToOne con Customer."""
    TAXPAYER = [('final','Final Consumer'),('ruc','RUC'),('rise','RISE')]
    PAYMENT = [('cash','Cash'),('credit_15','15 days'),('credit_30','30 days'),('credit_60','60 days')]
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='profile')
    taxpayer_type = models.CharField(max_length=10, choices=TAXPAYER, default='final')
    payment_terms = models.CharField(max_length=15, choices=PAYMENT, default='cash')
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    class Meta: verbose_name = 'Customer Profile'
    def __str__(self): return f'Profile: {self.customer}'

class Invoice(models.Model):
    """Cabecera de factura."""
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices', verbose_name='Cliente')
    invoice_date = models.DateTimeField(auto_now_add=True, verbose_name='Datos de Factura')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Impuesto')
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Total')
    is_active = models.BooleanField(default=True)
    tipo_pago = models.CharField(
        max_length=10,
        choices=[("CONTADO", "CONTADO"), ("CREDITO", "CREDITO")],
        default="CONTADO",
        verbose_name="Tipo de pago",
    )
    saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(
        max_length=15,
        choices=[("PENDIENTE", "PENDIENTE"), ("PAGADA", "PAGADA")],
        default="PENDIENTE",
    )
    class Meta: ordering = ['-invoice_date']
    def __str__(self): return f'Invoice #{self.id} - {self.customer}'

class ConfiguracionSistema(models.Model):
    """Configuración global del sistema (patrón singleton simple)."""
    iva_porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=15.00,
        verbose_name='IVA (%)',
        help_text='Porcentaje de IVA aplicado a facturas y compras. Ej: 15.00 = 15%.'
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración del Sistema'
        verbose_name_plural = 'Configuración del Sistema'

    def __str__(self):
        return f'IVA: {self.iva_porcentaje}%'

    @property
    def iva_display(self):
        """'15.00' -> '15', '12.50' -> '12.5' (sin coma decimal, sin ceros de más)."""
        return f'{self.iva_porcentaje:.2f}'.rstrip('0').rstrip('.')

    @classmethod
    def get_activa(cls):
        """Siempre hay un solo registro (patrón singleton simple)."""
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'iva_porcentaje': 15.00})
        return obj


class InvoiceDetail(models.Model):
    """Líneas de factura."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='details', verbose_name='Factura')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='invoice_details', verbose_name='Producto')
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Precio unitario')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    def __str__(self): return f'{self.product.name} x {self.quantity}'
    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_price
        super().save(*args, **kwargs)

