"""Condominios: distribución de gastos por alícuota y emisión de períodos."""
from decimal import Decimal

from apps.inmuebles.models import Cargo, GastoComun, PeriodoCondominio, Unidad
from apps.inmuebles.services import cobranza, condominio
from apps.inmuebles.services.cobranza import CobranzaError

from .base import InmueblesBase

PERIODO = '2026-10'


class DistribucionTests(InmueblesBase):

    def _gasto(self, monto, categoria='agua', periodo=PERIODO):
        return GastoComun.objects.create(edificio=self.edificio, periodo=periodo, categoria=categoria, descripcion=categoria, monto_usd=Decimal(monto), fecha=self.hoy)

    def test_vista_previa_reparte_por_alicuota_con_fondo_de_reserva(self):
        self._gasto('1000')
        vista = condominio.previsualizar_periodo(self.edificio, PERIODO)
        self.assertEqual(vista['total_gastos_usd'], '1000.00')
        self.assertEqual(vista['fondo_reserva_usd'], '100.00')  # 10%
        self.assertEqual(vista['total_a_distribuir_usd'], '1100.00')
        self.assertTrue(vista['alicuotas_completas'])
        montos = {f['codigo']: f['monto_usd'] for f in vista['unidades']}
        self.assertEqual(montos, {'A-1': '550.00', 'A-2': '330.00', 'A-3': '220.00'})

    def test_los_centavos_de_redondeo_no_se_pierden(self):
        for u in (self.u1, self.u2, self.u3):
            u.alicuota = Decimal('33.3333')
            u.save()
        self.u3.alicuota = Decimal('33.3334')
        self.u3.save()
        self.edificio.fondo_reserva_pct = Decimal('0')
        self.edificio.save()
        self._gasto('100.00')
        vista = condominio.previsualizar_periodo(self.edificio, PERIODO)
        total = sum(Decimal(f['monto_usd']) for f in vista['unidades'])
        self.assertEqual(total, Decimal('100.00'))

    def test_emitir_crea_una_cuota_por_unidad_y_no_se_repite(self):
        self._gasto('1000')
        periodo = condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        cargos = Cargo.objects.filter(periodo_condominio=periodo)
        self.assertEqual(cargos.count(), 3)
        self.assertEqual(sum(c.monto_usd for c in cargos), Decimal('1100.00'))
        self.assertEqual(cargos.get(unidad=self.u1).pagador, self.ana)
        self.assertEqual(cargos.get(unidad=self.u1).monto_fondo_usd, Decimal('50.00'))
        with self.assertRaises(CobranzaError):
            condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)

    def test_el_vencimiento_por_defecto_es_el_dia_configurado(self):
        self._gasto('100')
        periodo = condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        self.assertEqual(periodo.fecha_vencimiento.day, 5)
        self.assertGreater(periodo.fecha_vencimiento, self.hoy)

    def test_no_se_emite_sin_gastos_ni_con_alicuotas_incompletas(self):
        with self.assertRaises(CobranzaError):
            condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        self._gasto('100')
        self.u3.alicuota = Decimal('10.0000')
        self.u3.save()
        with self.assertRaises(CobranzaError):
            condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        periodo = condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user, forzar_alicuotas=True)
        # Con alícuotas que suman 90 se reparte en proporción: el edificio cobra todo igual.
        self.assertEqual(sum(c.monto_usd for c in periodo.cargos.all()), Decimal('110.00'))

    def test_un_periodo_emitido_no_admite_gastos_nuevos(self):
        self._gasto('100')
        condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        with self.assertRaises(CobranzaError):
            condominio.validar_gasto_editable(self.edificio, PERIODO)
        condominio.validar_gasto_editable(self.edificio, '2026-11')  # otro mes sí

    def test_anular_un_periodo_sin_pagos_permite_emitirlo_de_nuevo(self):
        self._gasto('100')
        periodo = condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        condominio.anular_periodo(periodo)
        self.assertEqual(Cargo.objects.filter(periodo_condominio=periodo, estado='pendiente').count(), 0)
        nuevo = condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        self.assertNotEqual(nuevo.pk, periodo.pk)
        self.assertEqual(PeriodoCondominio.objects.filter(edificio=self.edificio, periodo=PERIODO).exclude(estado='anulado').count(), 1)

    def test_no_se_anula_un_periodo_con_cuotas_pagadas(self):
        self._gasto('100')
        periodo = condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        cobranza.registrar_recibo(usuario=self.user, unidad=self.u1, fecha=self.hoy, monto_pago='10')
        with self.assertRaises(CobranzaError):
            condominio.anular_periodo(periodo)

    def test_el_saldo_a_favor_se_aplica_al_emitir(self):
        cobranza.registrar_recibo(usuario=self.user, unidad=self.u1, fecha=self.hoy, monto_pago='100')
        self._gasto('1000')
        periodo = condominio.emitir_periodo(self.edificio, PERIODO, usuario=self.user)
        cuota = periodo.cargos.get(unidad=self.u1)
        self.assertEqual(cuota.monto_pagado_usd, Decimal('100.00'))
        self.assertEqual(cobranza.saldo_a_favor_unidad(self.u1), Decimal('0.00'))

    def test_unidades_inactivas_o_sin_alicuota_no_reciben_cuota(self):
        otra = Unidad.objects.create(edificio=self.edificio, codigo='Z-9', alicuota=0, propietario=self.ana)
        self._gasto('100')
        vista = condominio.previsualizar_periodo(self.edificio, PERIODO)
        self.assertNotIn('Z-9', [f['codigo'] for f in vista['unidades']])
        self.assertTrue(any('alícuota 0' in a for a in vista['advertencias']))
        self.assertIsNotNone(otra.pk)
