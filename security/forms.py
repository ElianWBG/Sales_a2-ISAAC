from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User, Group, Permission


# === 1. CAMBIO DE CONTRASEÑA (no permitir reutilizar la actual) ===

class CambiarPasswordForm(PasswordChangeForm):
    """PasswordChangeForm que rechaza la nueva contraseña si es igual a la actual."""

    def clean_new_password1(self):
        new_password1 = self.cleaned_data.get('new_password1')
        if new_password1 and self.user.check_password(new_password1):
            raise forms.ValidationError(
                'La nueva contraseña no puede ser igual a la actual.',
                code='password_no_change',
            )
        return new_password1


# === 1.b CREACIÓN DE USUARIO POR EL ADMINISTRADOR (sin contraseña) ===

class AdminUserCreateForm(forms.ModelForm):
    """
    El Administrador crea la cuenta de otra persona (ej. un nuevo Vendedor).
    NO pide contraseña aquí: el sistema genera una temporal y se la envía
    por correo, junto con el usuario. Ver UserCreateView.
    """
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=True,
        label='Rol',
        empty_label='-- Selecciona un rol --',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'first_name': 'Nombres',
            'last_name': 'Apellidos',
            'email': 'Correo (aquí recibirá su contraseña temporal)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].widget.attrs['class'] = 'form-select'

    # El correo es el destino de la contraseña temporal y notificaciones del
    # sistema: si dos cuentas comparten correo, la persona recibe credenciales
    # de ambas cuentas mezcladas en su bandeja, sin poder distinguir a cuál
    # cuenta pertenece cada contraseña.
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError(
                'El correo es obligatorio: ahí se envía la contraseña temporal.'
            )
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'Ya existe un usuario registrado con este correo.'
            )
        return email


# === 2. EDICIÓN DE USUARIO (asignar un único rol) ===

class UserUpdateForm(forms.ModelForm):
    """El Administrador edita datos y el rol (único) de un usuario."""
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=True,
        label='Rol',
        empty_label='-- Selecciona un rol --',
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].widget.attrs['class'] = 'form-select'
        if self.instance.pk:
            current_role = self.instance.groups.first()
            if current_role:
                self.fields['role'].initial = current_role.pk

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            # Reemplaza por completo los roles del usuario: nunca múltiples.
            user.groups.set([self.cleaned_data['role']])
        return user

    # El correo es el destino de la contraseña temporal y notificaciones del
    # sistema: si dos cuentas comparten correo, la persona recibe credenciales
    # de ambas cuentas mezcladas en su bandeja, sin poder distinguir a cuál
    # cuenta pertenece cada contraseña.
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                'Ya existe un usuario registrado con este correo.'
            )
        return email


# === 3. ROLES (Group) CON SUS PERMISOS ===

class GroupForm(forms.ModelForm):
    """
    Crear/renombrar un rol. La asignación de permisos NO va aquí:
    vive exclusivamente en la matriz de 'security:role_permissions'
    para no tener dos caminos distintos que hacen lo mismo.
    """
    class Meta:
        model = Group
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}, ),
        }
        labels = {
            'name': 'Nombre del rol',
        }


# === 4. PERMISOS PERSONALIZADOS ===

class PermissionForm(forms.ModelForm):
    """Crear un permiso propio, ej: puede_aprobar_factura."""
    class Meta:
        model = Permission
        fields = ['name', 'codename', 'content_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'codename': forms.TextInput(attrs={'class': 'form-control'}),
            'content_type': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'name': 'Nombre',
            'codename': 'Código',
            'content_type': 'Tipo de contenido (modelo)',
        }
