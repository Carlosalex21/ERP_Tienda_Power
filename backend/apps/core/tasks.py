from celery import shared_task
from apps.core.whatsapp_service import WhatsAppService

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