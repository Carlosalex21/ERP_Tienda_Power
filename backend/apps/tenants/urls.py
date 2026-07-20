from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views_subscription import PlanViewSet, SubscriptionCUD, PlatformClientViewSet, TenantRegistrationView, SubdomainAvailabilityView
from .api.views_dashboard import PlatformDashboardView

router = DefaultRouter()
router.register(r'plans', PlanViewSet, basename='plan')
router.register(r'clients', PlatformClientViewSet, basename='platform-client')

urlpatterns = [
    # Endpoint para el registro de nuevos tenants (público)
    path('register/', TenantRegistrationView.as_view(), name='tenant-register'),

    # Endpoint para verificar disponibilidad de subdominio (público)
    path('check-subdomain/', SubdomainAvailabilityView.as_view(), name='check-subdomain'),

    
    # Endpoint para crear/actualizar una suscripción (requiere autenticación del dueño del tenant)
    path('subscriptions/', SubscriptionCUD.as_view(), name='subscription-cud'),

    # Endpoint para el dashboard del administrador de la plataforma
    path('dashboard/', PlatformDashboardView.as_view(), name='platform-dashboard'),

    # Endpoints para la gestión de la plataforma (admin)
    path('', include(router.urls)),
]