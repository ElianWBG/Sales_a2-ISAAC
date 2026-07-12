from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from security.views import CambiarPasswordView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Sobreescribe la vista de cambio de contraseña ANTES del include
    # genérico de abajo, para que esta gane la ruta 'password_change'
    # (necesaria para apagar must_change_password al guardar).
    path('accounts/password_change/', CambiarPasswordView.as_view(), name='password_change'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('security/', include('security.urls')),
    path('purchases/', include('purchasing.urls')),
    path('creditos-ventas/', include('creditos_ventas.urls')),
    path('', include('billing.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

