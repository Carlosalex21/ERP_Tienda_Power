"""Cobro de suscripciones: períodos con descuento y crédito por cambio de plan."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.tenants.models import Client, Plan, Subscription, SubscriptionPayment
from apps.tenants.services.subscription_payment_service import (
    PagoSuscripcionError, calcular_credito_por_cambio_de_plan, calcular_monto_a_cobrar, calcular_monto_periodo,
)

User = get_user_model()


class MontoPorPeriodoTests(TestCase):

    def test_descuentos_por_periodo(self):
        self.assertEqual(calcular_monto_periodo(Decimal('10'), 'mensual'), Decimal('10.00'))
        self.assertEqual(calcular_monto_periodo(Decimal('10'), 'trimestral'), Decimal('27.00'))  # 30 - 10%
        self.assertEqual(calcular_monto_periodo(Decimal('10'), 'anual'), Decimal('96.00'))  # 120 - 20%

    def test_periodo_invalido(self):
        with self.assertRaises(PagoSuscripcionError):
            calcular_monto_periodo(Decimal('10'), 'quincenal')


class CreditoPorCambioDePlanTests(TestCase):

    def setUp(self):
        owner = User.objects.create_user(username='owner_prorrateo', password='x')
        self.client_obj = Client.objects.create(schema_name='test_prorrateo', nombre_empresa='Prorrateo SA', owner=owner)
        self.basico = Plan.objects.create(nombre='Básico', precio=Decimal('10.00'))
        self.pro = Plan.objects.create(nombre='Pro', precio=Decimal('30.00'))

    def _suscribir(self, plan, dias_restantes, *, pagado=Decimal('10.00'), periodo='mensual'):
        Subscription.objects.update_or_create(
            client=self.client_obj,
            defaults={'plan': plan, 'estado': 'activa', 'fecha_fin': date.today() + timedelta(days=dias_restantes)},
        )
        SubscriptionPayment.objects.create(
            client=self.client_obj, plan=plan, periodo=periodo, monto=pagado, metodo='zelle',
            estado='confirmado', fecha_confirmacion=timezone.now(),
        )
        self.client_obj = Client.objects.get(pk=self.client_obj.pk)

    def test_sin_suscripcion_no_hay_credito(self):
        self.assertEqual(calcular_credito_por_cambio_de_plan(self.client_obj), Decimal('0.00'))

    def test_credito_proporcional_a_los_dias_que_quedan(self):
        self._suscribir(self.basico, dias_restantes=15)  # mitad del mes pagado
        self.assertEqual(calcular_credito_por_cambio_de_plan(self.client_obj), Decimal('5.00'))

    def test_upgrade_cobra_solo_la_diferencia(self):
        self._suscribir(self.basico, dias_restantes=15)
        cobro = calcular_monto_a_cobrar(self.client_obj, self.pro, 'mensual')
        self.assertEqual(cobro['monto_lista'], Decimal('30.00'))
        self.assertEqual(cobro['credito'], Decimal('5.00'))
        self.assertEqual(cobro['monto'], Decimal('25.00'))

    def test_renovar_el_mismo_plan_no_da_credito(self):
        self._suscribir(self.basico, dias_restantes=15)
        cobro = calcular_monto_a_cobrar(self.client_obj, self.basico, 'mensual')
        self.assertEqual(cobro['credito'], Decimal('0.00'))
        self.assertEqual(cobro['monto'], Decimal('10.00'))

    def test_con_muy_pocos_dias_casi_no_hay_credito(self):
        self._suscribir(self.basico, dias_restantes=1)
        cobro = calcular_monto_a_cobrar(self.client_obj, self.pro, 'mensual')
        self.assertEqual(cobro['credito'], Decimal('0.33'))
        self.assertEqual(cobro['monto'], Decimal('29.67'))

    def test_suscripcion_vencida_no_da_credito(self):
        self._suscribir(self.basico, dias_restantes=-3)
        self.assertEqual(calcular_credito_por_cambio_de_plan(self.client_obj), Decimal('0.00'))

    def test_el_credito_nunca_supera_el_precio_del_plan_nuevo(self):
        self._suscribir(self.pro, dias_restantes=30, pagado=Decimal('300.00'), periodo='anual')
        barato = Plan.objects.create(nombre='Mini', precio=Decimal('1.00'))
        cobro = calcular_monto_a_cobrar(self.client_obj, barato, 'mensual')
        self.assertEqual(cobro['monto'], Decimal('0.00'))
        self.assertLessEqual(cobro['credito'], cobro['monto_lista'])

    def test_plan_de_prueba_no_da_credito(self):
        prueba = Plan.objects.create(nombre='Plan de Prueba', precio=Decimal('0.00'))
        self._suscribir(prueba, dias_restantes=10, pagado=Decimal('5.00'))
        self.assertEqual(calcular_credito_por_cambio_de_plan(self.client_obj), Decimal('0.00'))
