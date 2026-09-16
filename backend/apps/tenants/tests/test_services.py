from django.test import TestCase
from datetime import date, timedelta
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
        self.assertEqual(sub.client, self.tenant)
        self.assertEqual(sub.plan, self.plan)
        self.assertEqual(sub.estado, 'activa')
        self.assertTrue(sub.fecha_fin > date.today())

    def test_renovacion_extiende_fecha_fin_en_vez_de_reiniciar(self):
        """Una renovación sobre una suscripción vigente debe sumar los días
        nuevos a la fecha_fin existente, no reiniciar desde hoy -- de lo
        contrario un cliente que renueva antes de vencer pierde los días que
        ya pagó y no usó."""
        hoy = date.today()
        fecha_fin_original = hoy + timedelta(days=20)
        Subscription.objects.create(
            client=self.tenant,
            plan=self.plan,
            estado='activa',
            fecha_inicio=hoy - timedelta(days=10),
            fecha_fin=fecha_fin_original,
        )

        sub = SubscriptionService.create_subscription(
            client_id=self.tenant.id, plan_id=self.plan.id, duration_days=30,
        )

        self.assertEqual(sub.fecha_fin, fecha_fin_original + timedelta(days=30))

    def test_activacion_sin_suscripcion_vigente_inicia_desde_hoy(self):
        """Si no hay suscripción previa vigente (nueva o ya vencida), la
        fecha_fin se calcula desde hoy, sin arrastrar nada."""
        hoy = date.today()
        Subscription.objects.create(
            client=self.tenant,
            plan=self.plan,
            estado='expirada',
            fecha_inicio=hoy - timedelta(days=40),
            fecha_fin=hoy - timedelta(days=10),
        )

        sub = SubscriptionService.create_subscription(
            client_id=self.tenant.id, plan_id=self.plan.id, duration_days=30,
        )

        self.assertEqual(sub.fecha_fin, hoy + timedelta(days=30))

    def test_check_expired_subscriptions(self):
        """Prueba que el servicio marca correctamente las suscripciones expiradas."""
        # Crear una suscripción que ya expiró
        Subscription.objects.create(
            client=self.tenant,
            plan=self.plan,
            estado='activa',
            fecha_inicio=date.today() - timedelta(days=31),
            fecha_fin=date.today() - timedelta(days=1)
        )
        
        expired_count = SubscriptionService.check_expired_subscriptions()
        self.assertEqual(expired_count, 1)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.subscription.estado, 'expirada')

