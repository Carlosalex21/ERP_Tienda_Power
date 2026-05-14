from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from ..models import Client, Plan, Subscription
from ..services.subscription_service import SubscriptionService

User = get_user_model()

class SubscriptionServiceTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='password')
        self.tenant = Client.objects.create(
            schema_name='test_tenant',
            nombre_empresa='Empresa de Prueba',
            owner=self.owner
        )
        self.plan = Plan.objects.create(nombre='Básico', precio=10.00)

    def test_create_subscription(self):
        """Prueba la creación exitosa de una suscripción."""
        sub = SubscriptionService.create_subscription(client_id=self.tenant.id, plan_id=self.plan.id)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.cliente, self.tenant)
        self.assertEqual(sub.plan, self.plan)
        self.assertEqual(sub.estado, 'activa')
        self.assertTrue(sub.fecha_fin > timezone.now())

    def test_check_expired_subscriptions(self):
        """Prueba que el servicio marca correctamente las suscripciones expiradas."""
        # Crear una suscripción que ya expiró
        Subscription.objects.create(
            cliente=self.tenant,
            plan=self.plan,
            estado='activa',
            fecha_inicio=timezone.now() - timedelta(days=31),
            fecha_fin=timezone.now() - timedelta(days=1)
        )
        
        expired_count = SubscriptionService.check_expired_subscriptions()
        self.assertEqual(expired_count, 1)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.subscription.estado, 'expirada')

