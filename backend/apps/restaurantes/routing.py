from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/restaurantes/publico/(?P<token>[^/]+)/$', consumers.PedidoMesaPublicoConsumer.as_asgi()),
    re_path(r'^ws/restaurantes/pedidos/(?P<pedido_id>\d+)/$', consumers.PedidoMesaPrivadoConsumer.as_asgi()),
    re_path(r'^ws/restaurantes/mesas/$', consumers.MesasConsumer.as_asgi()),
]
