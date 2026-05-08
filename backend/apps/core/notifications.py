import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

class EmailNotificationService:
    @staticmethod
    def send_email(subject, message, recipient_list):
        try:
            # Reemplazar por settings.DEFAULT_FROM_EMAIL en producción
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@powersaas.com')
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=False,
            )
            logger.info(f"Email enviado a {recipient_list}")
        except Exception as e:
            logger.error(f"Error enviando email: {str(e)}")

class PushNotificationService:
    @staticmethod
    def send_push(token, title, body, data=None):
        """
        Placeholder para integración con Firebase Cloud Messaging (FCM).
        Se requiere el SDK de firebase-admin.
        """
        # import firebase_admin
        # from firebase_admin import messaging
        #
        # message = messaging.Message(
        #     notification=messaging.Notification(
        #         title=title,
        #         body=body,
        #     ),
        #     data=data or {},
        #     token=token,
        # )
        # response = messaging.send(message)
        logger.info(f"Simulando Push Notification a {token}: {title} - {body}")
        pass

class NotificationService:
    """
    Fachada para manejar notificaciones del sistema de forma unificada.
    """
    
    @staticmethod
    def send_new_order_notification(tenant, orden_id, total):
        """
        Notifica al dueño del tenant que ha recibido una nueva orden externa.
        """
        subject = f"¡Nueva Orden Recibida! (#{orden_id})"
        message = f"Hola {tenant.nombre_empresa}, has recibido una nueva orden por un total de ${total}. Ingresa a tu panel para ver los detalles."
        
        # Enviar email al dueño
        if tenant.email_contacto:
            EmailNotificationService.send_email(
                subject=subject,
                message=message,
                recipient_list=[tenant.email_contacto]
            )
        
        # Aquí se obtendrían los tokens FCM del usuario dueño para enviarle el Push
        # tokens = TenantUser.objects.filter(is_owner=True).values_list('fcm_token', flat=True)
        # para simulación:
        PushNotificationService.send_push(
            token="dummy_token", 
            title=subject, 
            body=f"Nueva orden por ${total}"
        )
