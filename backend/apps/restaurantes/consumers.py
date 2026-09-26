"""
Consumers de WebSocket del módulo de Restaurante -- reemplazan el polling
(3-8s) de `PedidoMesaModal`, la cuenta pública y la grilla de mesas por un
push real cuando algo cambia (ver `apps.restaurantes.realtime`, que es quien
dispara estos mensajes desde las vistas normales de DRF).

Cada consumer, al conectar, manda el estado completo actual (lo mismo que
daría un GET) y luego vuelve a mandarlo completo cada vez que algo cambió --
se prefiere reenviar el objeto entero a mandar diffs: es lo mismo que ya
hacía el polling, así el frontend no necesita lógica de merge nueva.
"""
from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django_tenants.utils import get_public_schema_name, schema_context

from apps.core.permissions import ROL_ADMIN, ROL_VENDEDOR, codigo_rol

from .models import Mesa, PedidoMesa
from .api.serializers import MesaSerializer, PedidoMesaPublicoSerializer, PedidoMesaSerializer

logger = logging.getLogger(__name__)


@database_sync_to_async
def _es_staff_autorizado(user, schema_name) -> bool:
    # `user` ya se resolvió DENTRO de un `schema_context` en
    # `TenantJWTAuthMiddleware`, pero ese context manager solo dura esa
    # llamada -- `user.metadata` es un acceso perezoso (otra query) que
    # puede caer en un thread distinto del pool con el schema ya repuesto a
    # otra cosa. Hay que volver a entrar al schema correcto explícitamente
    # antes de tocar la relación, si no la consulta sale contra el schema
    # equivocado (o 'public', donde esta tabla ni existe).
    if not user or not user.is_authenticated:
        return False
    with schema_context(schema_name):
        if not hasattr(user, 'metadata'):
            return False
        return codigo_rol(user.metadata.rol) in (ROL_ADMIN, ROL_VENDEDOR)


def _schema_valido(schema_name) -> bool:
    """El esquema 'public' (o ninguno) nunca tiene tablas de `restaurantes` -- ni siquiera vale la pena consultar."""
    return bool(schema_name) and schema_name != get_public_schema_name()


class PedidoMesaPublicoConsumer(AsyncJsonWebsocketConsumer):
    """`/ws/restaurantes/publico/<token>/` -- lo mismo que ve un comensal por el QR, sin login."""

    async def connect(self):
        self.schema_name = self.scope.get('schema_name')
        self.token = self.scope['url_route']['kwargs']['token']
        self.group_name = f'pedido_publico_{self.schema_name}_{self.token}'

        if not _schema_valido(self.schema_name):
            await self.close(code=4004)
            return

        datos = await self._obtener_datos()
        if datos is None:
            await self.close(code=4004)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(datos)

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def _obtener_datos(self):
        try:
            with schema_context(self.schema_name):
                pedido = PedidoMesa.objects.select_related('mesa').prefetch_related('items__producto').filter(
                    token_publico=self.token,
                ).first()
                if pedido is None:
                    return None
                return PedidoMesaPublicoSerializer(pedido).data
        except Exception:
            logger.warning('Error resolviendo pedido público por WebSocket (schema=%s)', self.schema_name, exc_info=True)
            return None

    async def pedido_actualizado(self, event):
        await self.send_json(event['datos'])


class PedidoMesaPrivadoConsumer(AsyncJsonWebsocketConsumer):
    """`/ws/restaurantes/pedidos/<pedido_id>/` -- el modal del mesero, requiere sesión de staff."""

    async def connect(self):
        self.schema_name = self.scope.get('schema_name')
        self.pedido_id = self.scope['url_route']['kwargs']['pedido_id']
        self.group_name = f'pedido_privado_{self.schema_name}_{self.pedido_id}'

        if not _schema_valido(self.schema_name) or not await _es_staff_autorizado(self.scope.get('user'), self.schema_name):
            await self.close(code=4003)
            return

        datos = await self._obtener_datos()
        if datos is None:
            await self.close(code=4004)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(datos)

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def _obtener_datos(self):
        try:
            with schema_context(self.schema_name):
                pedido = PedidoMesa.objects.select_related('mesa', 'mesero', 'cliente').prefetch_related(
                    'items__producto',
                ).filter(pk=self.pedido_id).first()
                if pedido is None:
                    return None
                return PedidoMesaSerializer(pedido).data
        except Exception:
            logger.warning('Error resolviendo pedido privado por WebSocket (schema=%s)', self.schema_name, exc_info=True)
            return None

    async def pedido_actualizado(self, event):
        await self.send_json(event['datos'])


class MesasConsumer(AsyncJsonWebsocketConsumer):
    """`/ws/restaurantes/mesas/` -- la grilla completa, requiere sesión de staff."""

    async def connect(self):
        self.schema_name = self.scope.get('schema_name')
        self.group_name = f'mesas_{self.schema_name}'

        if not _schema_valido(self.schema_name) or not await _es_staff_autorizado(self.scope.get('user'), self.schema_name):
            await self.close(code=4003)
            return

        datos = await self._obtener_datos()
        if datos is None:
            await self.close(code=4004)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(datos)

    async def disconnect(self, code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def _obtener_datos(self):
        try:
            with schema_context(self.schema_name):
                mesas = Mesa.objects.filter(activo=True).order_by('numero')
                return MesaSerializer(mesas, many=True).data
        except Exception:
            logger.warning('Error resolviendo mesas por WebSocket (schema=%s)', self.schema_name, exc_info=True)
            return None

    async def mesas_actualizadas(self, event):
        await self.send_json(event['datos'])
