# apps/tenants/services/subscription_service.py
from datetime import timedelta
from django.utils import timezone
from tenants.models import Subscription, Plan, Client

class PaymentGatewayService:
    """
    Clase abstracta/base para la integración de pasarelas de pago.
    Aquí podríamos inyectar Stripe, PayPal o Pasarelas Locales.
    """
    def process_payment(self, amount, currency="USD", **kwargs):
        # Implementar la llamada a la API de la pasarela
        pass

    def create_customer(self, client):
        pass

class SubscriptionService:
    @staticmethod
    def create_subscription(client_id, plan_id, duration_days=30):
        """
        Crea una nueva suscripción para un cliente, asumiendo pago exitoso.
        """
        client = Client.objects.get(id=client_id)
        plan = Plan.objects.get(id=plan_id)
        
        # Inactivamos o cancelamos la suscripción anterior si existe
        if hasattr(client, 'subscription'):
            old_sub = client.subscription
            old_sub.estado = 'cancelada'
            old_sub.save()
            
        fecha_inicio = timezone.now()
        fecha_fin = fecha_inicio + timedelta(days=duration_days)
        
        # Para evitar problemas con OneToOneField si ya existe, podemos usar update_or_create
        # Pero como la vieja fue marcada como cancelada, lo ideal sería que 'cliente' en Subscription 
        # fuera ForeignKey si queremos historial. Dado que es OneToOne, la sobreescribimos o actualizamos.
        sub, created = Subscription.objects.update_or_create(
            cliente=client,
            defaults={
                'plan': plan,
                'estado': 'activa',
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin
            }
        )
        return sub

    @staticmethod
    def handle_payment_failure(client_id):
        """
        Lógica a ejecutar si un pago recurrente falla.
        """
        client = Client.objects.get(id=client_id)
        if hasattr(client, 'subscription'):
            sub = client.subscription
            sub.estado = 'pendiente'
            sub.save()
            
            # Aquí se puede notificar al usuario
        return client

    @staticmethod
    def check_expired_subscriptions():
        """
        Este método debería ser llamado por un Cron o Celery Task diariamente.
        """
        now = timezone.now()
        expired_subs = Subscription.objects.filter(estado='activa', fecha_fin__lt=now)
        for sub in expired_subs:
            sub.estado = 'expirada'
            sub.save()
            # Notificar expiración
        return expired_subs.count()
