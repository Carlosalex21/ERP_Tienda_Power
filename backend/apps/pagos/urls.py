from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    BancoViewSet,
    MetodoPagoConfigViewSet,
    PagoMovilConfigViewSet,
    ZelleConfigViewSet,
    StripeConfigViewSet,
    TransaccionPasarelaViewSet,
)

router = DefaultRouter()
router.register(r'bancos', BancoViewSet, basename='banco')
router.register(r'metodos-config', MetodoPagoConfigViewSet, basename='metodo-pago-config')
router.register(r'pagomovil-config', PagoMovilConfigViewSet, basename='pagomovil-config')
router.register(r'zelle-config', ZelleConfigViewSet, basename='zelle-config')
router.register(r'stripe-config', StripeConfigViewSet, basename='stripe-config')
router.register(r'transacciones-pasarela', TransaccionPasarelaViewSet, basename='transaccion-pasarela')

urlpatterns = [
    path('', include(router.urls)),
]