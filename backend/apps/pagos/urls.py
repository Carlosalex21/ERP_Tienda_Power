from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import MetodoPagoConfigViewSet, PagoMovilConfigViewSet, ZelleConfigViewSet, TransaccionPasarelaViewSet

router = DefaultRouter()
router.register(r'metodos-config', MetodoPagoConfigViewSet, basename='metodo-pago-config')
router.register(r'pagomovil-config', PagoMovilConfigViewSet, basename='pagomovil-config')
router.register(r'zelle-config', ZelleConfigViewSet, basename='zelle-config')
router.register(r'transacciones-pasarela', TransaccionPasarelaViewSet, basename='transaccion-pasarela')

urlpatterns = [
    path('', include(router.urls)),
]