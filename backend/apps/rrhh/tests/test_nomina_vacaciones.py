"""Nómina, vacaciones y liquidación: dinero de empleados, no puede fallar en silencio."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.core.testing import BaseTenantTestCase as TenantTestCase
from apps.rrhh.models import ConfiguracionRRHH, NominaEmpleado, PeriodoNomina
from apps.rrhh.services import (
    NominaError, agregar_concepto_manual, calcular_liquidacion, calcular_vacaciones,
    quitar_concepto_manual, registrar_vacacion_tomada,
)
from apps.usuarios.models import UserMetadata

User = get_user_model()


def _empleado(username='ana', *, contratado_hace_dias=730, sueldo=Decimal('300.00')):
    usuario = User.objects.create_user(username=username, password='x')
    UserMetadata.objects.create(
        user=usuario,
        fecha_contratacion=date.today() - timedelta(days=contratado_hace_dias) if contratado_hace_dias is not None else None,
        sueldo_base=sueldo,
    )
    return User.objects.get(pk=usuario.pk)


class VacacionesYLiquidacionTests(TenantTestCase):

    def setUp(self):
        ConfiguracionRRHH.objects.update_or_create(
            pk=1, defaults={'dias_vacaciones_por_anio': 15, 'dias_prestaciones_por_anio': 30, 'dias_periodo_sueldo_base': 30},
        )
        self.empleado = _empleado()

    def test_dias_acumulados_por_antiguedad(self):
        resultado = calcular_vacaciones(self.empleado)
        self.assertEqual(resultado['antiguedad_anios'], Decimal('2.00'))
        self.assertEqual(resultado['dias_acumulados'], 30)
        self.assertEqual(resultado['dias_disponibles'], 30)

    def test_las_vacaciones_tomadas_descuentan_del_saldo(self):
        hoy = date.today()
        registrar_vacacion_tomada(self.empleado, fecha_inicio=hoy - timedelta(days=20), fecha_fin=hoy - timedelta(days=11))
        resultado = calcular_vacaciones(self.empleado)
        self.assertEqual(resultado['dias_tomados'], 10)
        self.assertEqual(resultado['dias_disponibles'], 20)

    def test_rango_de_vacaciones_invertido(self):
        hoy = date.today()
        with self.assertRaises(NominaError):
            registrar_vacacion_tomada(self.empleado, fecha_inicio=hoy, fecha_fin=hoy - timedelta(days=1))

    def test_sin_fecha_de_contratacion_no_inventa_antiguedad(self):
        sin_fecha = _empleado('sin_fecha', contratado_hace_dias=None)
        self.assertEqual(calcular_vacaciones(sin_fecha)['dias_acumulados'], 0)
        with self.assertRaises(NominaError):
            calcular_liquidacion(sin_fecha, date.today())

    def test_liquidacion_suma_vacaciones_pendientes_y_prestaciones(self):
        hoy = date.today()
        registrar_vacacion_tomada(self.empleado, fecha_inicio=hoy - timedelta(days=20), fecha_fin=hoy - timedelta(days=11))
        liquidacion = calcular_liquidacion(self.empleado, hoy)
        # sueldo diario 300 / 30 = 10; 20 días de vacaciones pendientes; 2 años x 30 días de prestaciones.
        self.assertEqual(liquidacion['sueldo_diario'], Decimal('10.00'))
        self.assertEqual(liquidacion['monto_vacaciones_pendientes'], Decimal('200.00'))
        self.assertEqual(liquidacion['monto_prestaciones'], Decimal('600.00'))
        self.assertEqual(liquidacion['total_liquidacion'], Decimal('800.00'))

    def test_liquidacion_con_saldo_negativo_no_resta(self):
        hoy = date.today()
        registrar_vacacion_tomada(self.empleado, fecha_inicio=hoy - timedelta(days=60), fecha_fin=hoy - timedelta(days=1))  # 60 > 30
        liquidacion = calcular_liquidacion(self.empleado, hoy)
        self.assertEqual(liquidacion['dias_vacaciones_pendientes'], 0)
        self.assertEqual(liquidacion['monto_vacaciones_pendientes'], Decimal('0.00'))

    def test_egreso_anterior_a_la_contratacion(self):
        with self.assertRaises(NominaError):
            calcular_liquidacion(self.empleado, date.today() - timedelta(days=5000))

    def test_sin_sueldo_no_se_puede_liquidar(self):
        sin_sueldo = _empleado('sin_sueldo', sueldo=None)
        with self.assertRaises(NominaError):
            calcular_liquidacion(sin_sueldo, date.today())


class ConceptosManualesTests(TenantTestCase):

    def setUp(self):
        self.empleado = _empleado('luis', sueldo=Decimal('1000.00'))
        self.periodo = PeriodoNomina.objects.create(fecha_desde=date(2026, 9, 1), fecha_hasta=date(2026, 9, 15))
        self.linea = NominaEmpleado.objects.create(
            periodo=self.periodo, usuario=self.empleado, sueldo_base=Decimal('1000.00'),
            deduccion_ausencias=Decimal('50.00'), pago_horas_extra=Decimal('20.00'), total_pagar=Decimal('970.00'),
        )

    def test_bono_y_deduccion_recalculan_el_total(self):
        agregar_concepto_manual(self.linea, nombre='Comisión', tipo='bono', monto=Decimal('100.00'))
        agregar_concepto_manual(self.linea, nombre='Adelanto', tipo='deduccion', monto=Decimal('30.00'))
        self.linea.refresh_from_db()
        # 1000 - 50 + 20 + 100 - 30
        self.assertEqual(self.linea.total_pagar, Decimal('1040.00'))
        self.assertEqual(self.linea.bonificaciones, Decimal('100.00'))
        self.assertEqual(self.linea.otras_deducciones, Decimal('30.00'))

    def test_quitar_concepto_restaura_el_total(self):
        agregar_concepto_manual(self.linea, nombre='Comisión', tipo='bono', monto=Decimal('100.00'))
        concepto = self.linea.conceptos.get()
        quitar_concepto_manual(concepto)
        self.linea.refresh_from_db()
        self.assertEqual(self.linea.total_pagar, Decimal('970.00'))

    def test_monto_cero_o_tipo_invalido(self):
        with self.assertRaises(NominaError):
            agregar_concepto_manual(self.linea, nombre='X', tipo='bono', monto=Decimal('0'))
        with self.assertRaises(NominaError):
            agregar_concepto_manual(self.linea, nombre='X', tipo='regalo', monto=Decimal('5'))

    def test_periodo_pagado_no_admite_cambios(self):
        self.periodo.estado = 'pagada'
        self.periodo.save()
        with self.assertRaises(NominaError):
            agregar_concepto_manual(self.linea, nombre='Tarde', tipo='bono', monto=Decimal('10'))
