from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Módulos del Sistema
    path('api/v1/auth/', include('apps.usuarios.urls')),
    path('api/v1/facturacion/', include('apps.facturacion.urls')),
    path('api/v1/inventario/', include('apps.inventario.urls')),
    path('api/v1/rrhh/', include('apps.rrhh.urls')),
    path('api/v1/reportes/', include('apps.reportes.urls')),
    path('api/v1/configuracion/', include('apps.configuracion.urls')),
    path('api/v1/clientes/', include('apps.clientes.urls')),
    path('api/v1/proveedores/', include('apps.proveedores.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)