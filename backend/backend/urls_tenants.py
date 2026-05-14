from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView, 
    SpectacularRedocView, 
    SpectacularSwaggerView
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # =================================================================
    # DOCUMENTACIÓN DE API (OpenAPI 3) para el ESQUEMA DEL TENANT
    # drf-spectacular agrupará automáticamente las APIs por el primer 
    # segmento de la URL (ej: 'facturacion', 'inventario').
    # =================================================================
    path('api/schema/', SpectacularAPIView.as_view(urlconf='backend.urls_tenants'), name='schema'),
    path(
        'api/docs/', 
        SpectacularSwaggerView.as_view(url_name='schema'), 
        name='swagger-ui'
    ),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Modulos del Sistema
    path('api/v1/auth/', include('apps.usuarios.urls')),
    path('api/v1/facturacion/', include('apps.facturacion.urls')),
    path('api/v1/inventario/', include('apps.inventario.urls')),
    path('api/v1/rrhh/', include('apps.rrhh.urls')),
    path('api/v1/reportes/', include('apps.reportes.urls')),
    path('api/v1/configuracion/', include('apps.configuracion.urls')),
    path('api/v1/clientes/', include('apps.clientes.urls')),
    path('api/v1/proveedores/', include('apps.proveedores.urls')),
    path('api/v1/pagos/', include('apps.pagos.urls')), # Nueva app de pagos
    
    # URLs publicas para el catalogo y pedidos del cliente
    path('api/v1/public/', include('apps.facturacion.urls_public')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

def debug_tenant(request):
    return JsonResponse({
        'tenant': getattr(request, 'tenant', 'No detectado').schema_name,
        'urlconf': getattr(request, 'urlconf', 'ROOT_URLCONF por defecto'),
        'host': request.get_host(),
    })

# Añádelo a tus urlpatterns
urlpatterns += [
    path('api/debug-tenant/', debug_tenant),
]