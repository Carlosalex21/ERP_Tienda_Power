from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView, 
    SpectacularRedocView, 
    SpectacularSwaggerView,
)
from apps.tenants.api.views_subscription import (
    TenantProfileView, PlanViewSet, PeriodosSuscripcionView, PlatformPaymentInfoView,
    CrearPagoSuscripcionDesdeAdminView, TasaBcvPlataformaView,
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
    # Endpoint para que el frontend obtenga el perfil del tenant actual
    path('api/v1/tenants/profile/', TenantProfileView.as_view(), name='tenant-profile'),
    # Gestión del plan/suscripción DESDE el propio panel del tenant (sin
    # tener que cruzar al dominio raíz e iniciar sesión de nuevo como el
    # dueño) -- estos modelos viven en el esquema público (SHARED_APPS),
    # pero sus vistas de lectura/creación de pago también deben quedar
    # accesibles vía el urlconf del tenant.
    path('api/v1/tenants/plans/', PlanViewSet.as_view({'get': 'list'}), name='tenant-plans-list'),
    path('api/v1/tenants/periodos-suscripcion/', PeriodosSuscripcionView.as_view(), name='tenant-periodos-suscripcion'),
    path('api/v1/tenants/payment-info/', PlatformPaymentInfoView.as_view(), name='tenant-payment-info'),
    path('api/v1/tenants/tasa-bcv/', TasaBcvPlataformaView.as_view(), name='tenant-tasa-bcv'),
    path('api/v1/tenants/pagos-suscripcion-admin/', CrearPagoSuscripcionDesdeAdminView.as_view(), name='tenant-crear-pago-suscripcion'),
    path('api/v1/configuracion/', include('apps.configuracion.urls')),
    path('api/v1/auditoria/', include('apps.auditoria.urls')),
    path('api/v1/clientes/', include('apps.clientes.urls')),
    path('api/v1/proveedores/', include('apps.proveedores.urls')),
    path('api/v1/pagos/', include('apps.pagos.urls')), # Nueva app de pagos
    
    # URLs publicas para el catalogo y pedidos del cliente
    path('api/v1/public/', include('apps.catalogo_publico.urls')),

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