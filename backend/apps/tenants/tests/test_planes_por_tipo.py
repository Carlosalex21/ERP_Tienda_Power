"""Un tenant solo puede contratar/renovar planes de su propio tipo de negocio."""
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.tenants.models import Plan
from apps.tenants.services import subscription_payment_service as servicio


class PlanAplicaATests(SimpleTestCase):
    def test_plan_sin_tipos_aplica_a_todos(self):
        self.assertTrue(Plan(tipos_negocio=[]).aplica_a("restaurante"))

    def test_plan_restringido(self):
        plan = Plan(tipos_negocio=["restaurante"])
        self.assertTrue(plan.aplica_a("restaurante"))
        self.assertFalse(plan.aplica_a("retail"))


class CrearPagoValidaTipoTests(SimpleTestCase):
    def test_rechaza_plan_de_otro_modulo(self):
        cliente = SimpleNamespace(pais_codigo="VE", tipo_negocio="restaurante")
        plan = Plan(nombre="Retail Pro", precio=Decimal("20"), tipos_negocio=["retail"])
        with self.assertRaisesMessage(servicio.PagoSuscripcionError, "tipo de negocio"):
            servicio.crear_pago_suscripcion(client=cliente, plan=plan, metodo="pago_movil")
