from django.urls import path

from .api.views import (
    CatalogoPublicoView,
    CrearPedidoPublicoView,
    MetodosPagoPublicoView,
    EmpresaInfoPublicaView,
    TasasPublicasView,
    CrearSesionStripeView,
    StripeWebhookView,
)

urlpatterns = [
    path('catalogo/', CatalogoPublicoView.as_view(), name='public-catalog'),
    path('ordenar/', CrearPedidoPublicoView.as_view(), name='public-create-order'),
    path('metodos-pago/', MetodosPagoPublicoView.as_view(), name='public-metodos-pago'),
    path('info/', EmpresaInfoPublicaView.as_view(), name='public-empresa-info'),
    path('tasas/', TasasPublicasView.as_view(), name='public-tasas'),
    path('pagos/stripe/sesion/', CrearSesionStripeView.as_view(), name='public-stripe-session'),
    path('pagos/stripe/webhook/', StripeWebhookView.as_view(), name='public-stripe-webhook'),
]
