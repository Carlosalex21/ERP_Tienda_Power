from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views_subscription import (
    PlanViewSet, SubscriptionCUD, PlatformClientViewSet, TenantRegistrationView, SubdomainAvailabilityView,
    UsernameAvailabilityView, MiClienteView, PlatformPaymentInfoView, PlatformPaymentConfigView, CrearPagoSuscripcionView,
    StripeSuscripcionWebhookView, SubscriptionPaymentViewSet, RegistrationQuotaView, PlatformSettingsView,
    PeriodosSuscripcionView, TasaBcvPlataformaView,
)
from .api.views_dashboard import PlatformDashboardView

router = DefaultRouter()
router.register(r'plans', PlanViewSet, basename='plan')
router.register(r'clients', PlatformClientViewSet, basename='platform-client')
router.register(r'subscription-payments', SubscriptionPaymentViewSet, basename='subscription-payment')

urlpatterns = [
    # Endpoint para el registro de nuevos tenants (público)
    path('register/', TenantRegistrationView.as_view(), name='tenant-register'),

    # Endpoint para verificar disponibilidad de subdominio (público)
    path('check-subdomain/', SubdomainAvailabilityView.as_view(), name='check-subdomain'),

    # Endpoint para verificar disponibilidad de nombre de usuario (público)
    path('check-username/', UsernameAvailabilityView.as_view(), name='check-username'),

    # Cupo de registros gratuitos restantes (público) y configuración global (admin)
    path('registration-quota/', RegistrationQuotaView.as_view(), name='registration-quota'),
    path('settings/', PlatformSettingsView.as_view(), name='platform-settings'),


    # Endpoint para crear/actualizar una suscripción (requiere autenticación del dueño del tenant)
    path('subscriptions/', SubscriptionCUD.as_view(), name='subscription-cud'),

    # Endpoint para el dashboard del administrador de la plataforma
    path('dashboard/', PlatformDashboardView.as_view(), name='platform-dashboard'),

    # --- Cobro de suscripciones SaaS (el tenant le paga a la plataforma) ---
    path('mi-cliente/', MiClienteView.as_view(), name='mi-cliente'),
    path('payment-info/', PlatformPaymentInfoView.as_view(), name='platform-payment-info'),
    path('tasa-bcv/', TasaBcvPlataformaView.as_view(), name='platform-tasa-bcv'),
    path('payment-config/', PlatformPaymentConfigView.as_view(), name='platform-payment-config'),
    path('pagos-suscripcion/', CrearPagoSuscripcionView.as_view(), name='crear-pago-suscripcion'),
    path('periodos-suscripcion/', PeriodosSuscripcionView.as_view(), name='periodos-suscripcion'),
    path('pagos-suscripcion/stripe/webhook/', StripeSuscripcionWebhookView.as_view(), name='stripe-suscripcion-webhook'),

    # Endpoints para la gestión de la plataforma (admin)
    path('', include(router.urls)),
]