"""
Helpers para avisar por WebSocket cuando algo de un pedido de mesa cambió --
llamados desde las vistas normales de DRF (sync/WSGI) después de cada
mutación (agregar/quitar ítem, cerrar, llamar mesero, pedir cuenta, cambiar
propina/división/datos de pago). `async_to_sync` es el puente estándar de
Channels para mandar al channel layer desde código síncrono.

Todo esto es fail-open a propósito, igual que otros side-effects "avisar a
otro sistema" en este proyecto (ver `apps.contabilidad.services.
generar_asiento_automatico_venta`): si Redis está caído o el channel layer
falla por lo que sea, el pedido/factura YA se guardó -- nunca debe revertirse
ni bloquearse una operación real por no poder avisar en vivo. Los clientes
conectados simplemente no reciben el push y se quedan con el estado anterior
hasta que reconecten o (en el frontend) caigan al fallback de polling.
"""
from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connection

from .api.serializers import MesaSerializer, PedidoMesaPublicoSerializer, PedidoMesaSerializer
from .models import Mesa, PedidoMesa

logger = logging.getLogger(__name__)


def _enviar(grupo: str, tipo: str, datos: dict) -> None:
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(grupo, {"type": tipo, "datos": datos})
    except Exception:
        logger.warning("No se pudo enviar el evento en vivo al grupo %s", grupo, exc_info=True)


def notificar_pedido_actualizado(pedido: PedidoMesa) -> None:
    """
    Avisa tanto a quien tiene abierta la cuenta pública (QR) como al panel
    del mesero para ESTE pedido. Nunca debe poder tumbar la vista que la
    llama (agregar_item, cerrar, etc.) -- esa mutación YA se guardó; un
    problema para avisar en vivo no puede convertir una operación exitosa en
    un 500 para el usuario.
    """
    try:
        schema_name = connection.schema_name
        datos_publico = PedidoMesaPublicoSerializer(pedido).data
        _enviar(f'pedido_publico_{schema_name}_{pedido.token_publico}', 'pedido_actualizado', datos_publico)

        datos_privado = PedidoMesaSerializer(pedido).data
        _enviar(f'pedido_privado_{schema_name}_{pedido.id}', 'pedido_actualizado', datos_privado)
    except Exception:
        logger.warning('No se pudo preparar el evento en vivo del pedido %s', pedido.id, exc_info=True)

    # El estado de la mesa (ocupada/libre, llaman al mesero, piden la cuenta)
    # también puede haber cambiado -- la grilla necesita enterarse aunque
    # nadie tenga abierto el modal de ESTA mesa puntual.
    notificar_mesas_actualizadas()


def notificar_mesas_actualizadas() -> None:
    """Avisa a la grilla de mesas del panel -- se llama tras abrir/cerrar/cancelar un pedido o cambiar sus banderas."""
    try:
        schema_name = connection.schema_name
        mesas = Mesa.objects.filter(activo=True).order_by('numero')
        datos = MesaSerializer(mesas, many=True).data
        _enviar(f'mesas_{schema_name}', 'mesas_actualizadas', datos)
    except Exception:
        logger.warning('No se pudo preparar el evento en vivo de la grilla de mesas', exc_info=True)
