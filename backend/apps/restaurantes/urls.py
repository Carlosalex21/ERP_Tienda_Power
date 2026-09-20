from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.views import (
    MesaViewSet,
    PedidoMesaViewSet,
    PedidoMesaPublicoView,
    LlamarMeseroPublicoView,
    PedirCuentaPublicoView,
)

router = DefaultRouter()
router.register(r'mesas', MesaViewSet, basename='mesa')
router.register(r'pedidos', PedidoMesaViewSet, basename='pedido-mesa')

urlpatterns = [
    # Público (sin sesión) -- accedido desde el QR de la mesa, no desde el panel.
    path('publico/<str:token>/', PedidoMesaPublicoView.as_view(), name='pedido-mesa-publico'),
    path('publico/<str:token>/llamar-mesero/', LlamarMeseroPublicoView.as_view(), name='pedido-mesa-llamar-mesero'),
    path('publico/<str:token>/pedir-cuenta/', PedirCuentaPublicoView.as_view(), name='pedido-mesa-pedir-cuenta'),

    path('', include(router.urls)),
]
