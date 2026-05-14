from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # DOCUMENTACIÓN DE API (Esquema Público)
    path('api/schema/', SpectacularAPIView.as_view(urlconf='backend.urls_public'), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # APIs Globales (SHARED_APPS) 
    path('api/v1/tenants/', include('apps.tenants.urls')),

    # Autenticación para los dueños de los tenants (en el esquema público)
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair_public'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh_public'),
]

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