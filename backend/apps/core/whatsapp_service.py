import logging

logger = logging.getLogger(__name__)

class WhatsAppService:
    """
    Servicio de simulación para enviar notificaciones de WhatsApp.
    En un futuro, esto se integraría con una API real (ej. Twilio, Meta API).
    """
    @staticmethod
    def send_message(phone_number, message):
        """
        Simula el envío de un mensaje de WhatsApp.
        
        :param phone_number: Número de teléfono del destinatario (ej: '+584121234567')
        :param message: El texto del mensaje a enviar.
        """
        # Aquí iría la lógica para llamar a la API de WhatsApp
        logger.info(f"--- SIMULANDO ENVÍO DE WHATSAPP ---")
        logger.info(f"Destino: {phone_number}")
        logger.info(f"Mensaje: {message}")
        logger.info(f"------------------------------------")
        # En un caso real, manejaríamos la respuesta de la API.
        return True