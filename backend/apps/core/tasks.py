import logging

from celery import shared_task
from apps.core.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)

@shared_task
def send_whatsapp_message_task(phone_number, message):
    """
    Tarea de Celery para enviar un mensaje de WhatsApp en segundo plano.
    """
    try:
        WhatsAppService.send_message(phone_number, message)
        return f"Mensaje de WhatsApp enviado a {phone_number}"
    except Exception as e:
        return f"Error al enviar mensaje de WhatsApp a {phone_number}: {e}"


def dispatch_task(task, *args, **kwargs) -> bool:
    """
    Despacha una tarea de Celery (``task.delay(*args, **kwargs)``) sin dejar
    que una caída del broker (Redis/RabbitMQ no disponible) tumbe la
    petición HTTP que la dispara.

    Antes, cualquier vista que llamara `.delay()` directamente (crear un
    pedido público, reducir stock con sync a WooCommerce, etc.) devolvía un
    500 completo -- incluso cuando la operación principal (crear la
    factura, descontar el stock) ya se había completado con éxito -- en
    cuanto el broker no respondía. Estas notificaciones/sincronizaciones son
    en segundo plano por definición: mejor perderlas con una advertencia en
    el log que romper la operación que sí importa.

    Returns:
        bool: True si se pudo encolar, False si se degradó silenciosamente.
    """
    try:
        task.delay(*args, **kwargs)
        return True
    except Exception as exc:  # noqa: BLE001 - un broker caído no debe romper la request
        logger.warning("No se pudo encolar la tarea '%s': %s", getattr(task, "name", task), exc)
        return False