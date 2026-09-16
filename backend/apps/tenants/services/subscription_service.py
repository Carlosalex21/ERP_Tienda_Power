# apps/tenants/services/subscription_service.py
from datetime import date, timedelta
from apps.tenants.models import Subscription, Plan, Client

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
        Activa o renueva la suscripción de un cliente, asumiendo pago exitoso.

        Si el cliente ya tiene una suscripción vigente (activa y con
        `fecha_fin` en el futuro), la renovación EXTIENDE esa fecha_fin en
        vez de reiniciarla desde hoy -- de lo contrario un cliente que paga
        por adelantado (ej. renueva unos días antes de vencer) perdería los
        días que ya pagó y no usó.
        """
        client = Client.objects.get(id=client_id)
        plan = Plan.objects.get(id=plan_id)

        old_sub = getattr(client, 'subscription', None)
        # `date.today()` (no `timezone.now().date()`) a propósito -- ver la
        # nota equivalente en `apps.configuracion.services.bcv_service`:
        # `fecha_fin`/`fecha_inicio` son `DateField`, que Django graba con
        # `datetime.date.today()` (hora del SO, sin pasar por `TIME_ZONE`).
        # Con `TIME_ZONE="UTC"` y el SO en otra zona horaria,
        # `timezone.now().date()` puede irse un día por delante y romper la
        # comparación "¿la suscripción sigue vigente?".
        hoy = date.today()
        if old_sub and old_sub.estado == 'activa' and old_sub.fecha_fin and old_sub.fecha_fin >= hoy:
            fecha_inicio = old_sub.fecha_inicio
            fecha_fin = old_sub.fecha_fin + timedelta(days=duration_days)
        else:
            fecha_inicio = hoy
            fecha_fin = hoy + timedelta(days=duration_days)

        sub, created = Subscription.objects.update_or_create(
            client=client,
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
        # Mismo motivo que en `create_subscription`: comparar contra `hoy`
        # (fecha del SO) en vez de la fecha derivada de `timezone.now()`.
        hoy = date.today()
        expired_subs = Subscription.objects.filter(estado='activa', fecha_fin__lt=hoy)
        for sub in expired_subs:
            sub.estado = 'expirada'
            sub.save()
            # Notificar expiración
        return expired_subs.count()
