"""Cobranza: pagos, aplicación a deudas, créditos, anulaciones y mora."""
from decimal import Decimal

from apps.inmuebles.models import Cargo, Recibo
from apps.inmuebles.services import cobranza
from apps.inmuebles.services.cobranza import CobranzaError

from .base import InmueblesBase, TASA


class RecibosTests(InmueblesBase):

    def _cargo(self, unidad, monto, vence_en, tipo='cuota_condominio', periodo=None):
        return cobranza.crear_cargo(
            unidad=unidad, tipo=tipo, concepto=f'Cuota {periodo or vence_en}', periodo=periodo or '2026-01',
            monto_usd=monto, fecha_vencimiento=self.dias(vence_en), fecha_emision=self.dias(-60),
        )

    def _pagar(self, unidad, monto, **kw):
        datos = dict(usuario=self.user, unidad=unidad, fecha=self.hoy, monto_pago=monto, moneda_pago='USD')
        datos.update(kw)
        return cobranza.registrar_recibo(**datos)

    def test_el_pago_salda_primero_la_deuda_mas_antigua(self):
        vieja = self._cargo(self.u1, '100', -40, periodo='2026-01')
        nueva = self._cargo(self.u1, '100', -10, periodo='2026-02')
        recibo = self._pagar(self.u1, '130')
        vieja.refresh_from_db()
        nueva.refresh_from_db()
        self.assertEqual((vieja.estado, vieja.monto_pagado_usd), ('pagado', Decimal('100.00')))
        self.assertEqual((nueva.estado, nueva.monto_pagado_usd), ('pendiente', Decimal('30.00')))
        self.assertEqual(recibo.monto_disponible_usd, Decimal('0.00'))
        self.assertEqual(recibo.numero, 'REC-000001')

    def test_lo_que_sobra_queda_como_saldo_a_favor_y_se_aplica_a_la_siguiente_cuota(self):
        self._cargo(self.u1, '50', -5)
        recibo = self._pagar(self.u1, '80')
        self.assertEqual(recibo.monto_disponible_usd, Decimal('30.00'))
        self.assertEqual(cobranza.saldo_a_favor_unidad(self.u1), Decimal('30.00'))

        nuevo = self._cargo(self.u1, '100', 10, periodo='2026-03')
        aplicado = cobranza.aplicar_creditos(self.u1)
        nuevo.refresh_from_db()
        self.assertEqual(aplicado, Decimal('30.00'))
        self.assertEqual(nuevo.monto_pagado_usd, Decimal('30.00'))
        self.assertEqual(cobranza.saldo_a_favor_unidad(self.u1), Decimal('0.00'))

    def test_pago_en_bolivares_se_convierte_con_la_tasa(self):
        self._cargo(self.u1, '10', -1)
        recibo = self._pagar(self.u1, '400', moneda_pago='VES', tasa=TASA)
        self.assertEqual(recibo.monto_usd, Decimal('10.00'))
        self.assertEqual(recibo.tasa, TASA)

    def test_pago_en_bolivares_toma_la_tasa_vigente_si_no_se_indica(self):
        recibo = self._pagar(self.u1, '800', moneda_pago='VES')
        self.assertEqual(recibo.monto_usd, Decimal('20.00'))

    def test_monedas_no_aceptadas_y_montos_invalidos(self):
        with self.assertRaises(CobranzaError):
            self._pagar(self.u1, '10', moneda_pago='EUR')
        with self.assertRaises(CobranzaError):
            self._pagar(self.u1, '0')
        with self.assertRaises(CobranzaError):
            self._pagar(self.u1, '10', fecha=self.dias(1))

    def test_pagar_dos_veces_la_misma_referencia_se_rechaza(self):
        self._pagar(self.u1, '25', referencia='REF-1')
        with self.assertRaises(CobranzaError):
            self._pagar(self.u1, '25', referencia='REF-1')
        self.assertEqual(Recibo.objects.count(), 1)

    def test_pagar_deudas_elegidas(self):
        a = self._cargo(self.u1, '100', -40, periodo='2026-01')
        b = self._cargo(self.u1, '60', -10, periodo='2026-02')
        self._pagar(self.u1, '60', cargos=[b])
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.estado, 'pagado')
        self.assertEqual(a.monto_pagado_usd, Decimal('0.00'))

    def test_no_se_puede_pagar_una_deuda_de_otra_unidad(self):
        ajena = self._cargo(self.u2, '10', -1)
        with self.assertRaises(CobranzaError):
            self._pagar(self.u1, '10', cargos=[ajena])

    def test_anular_el_recibo_restaura_las_deudas(self):
        cargo = self._cargo(self.u1, '100', -5)
        recibo = self._pagar(self.u1, '100')
        cobranza.anular_recibo(recibo, motivo='Error de captura')
        cargo.refresh_from_db()
        recibo.refresh_from_db()
        self.assertEqual((cargo.estado, cargo.monto_pagado_usd), ('pendiente', Decimal('0.00')))
        self.assertEqual(recibo.estado, 'anulado')
        with self.assertRaises(CobranzaError):
            cobranza.anular_recibo(recibo)

    def test_no_se_anula_un_cargo_con_pagos(self):
        cargo = self._cargo(self.u1, '100', -5)
        self._pagar(self.u1, '10')
        with self.assertRaises(CobranzaError):
            cobranza.anular_cargo(cargo)
        libre = self._cargo(self.u2, '10', 5)
        self.assertEqual(cobranza.anular_cargo(libre).estado, 'anulado')

    def test_el_correlativo_de_recibos_es_consecutivo(self):
        numeros = [self._pagar(self.u1, '5', referencia=f'R{i}').numero for i in range(3)]
        self.assertEqual(numeros, ['REC-000001', 'REC-000002', 'REC-000003'])


class MoraTests(InmueblesBase):

    def _vencido(self, unidad, monto, dias_vencido):
        return cobranza.crear_cargo(
            unidad=unidad, tipo='cuota_condominio', concepto='Cuota', periodo='2026-01', monto_usd=monto,
            fecha_vencimiento=self.dias(-dias_vencido), fecha_emision=self.dias(-dias_vencido - 30),
        )

    def test_mora_porcentual_sobre_el_saldo_una_vez_por_mes(self):
        cargo = self._vencido(self.u1, '100', 10)
        self.assertEqual(cobranza.aplicar_mora(self.hoy), 1)
        mora = Cargo.objects.get(tipo='mora')
        self.assertEqual(mora.monto_usd, Decimal('2.00'))  # 2% de 100
        self.assertEqual(mora.cargo_origen, cargo)
        self.assertEqual(cobranza.aplicar_mora(self.hoy), 0, 'idempotente: no repite la mora del mes')
        self.assertEqual(Cargo.objects.filter(tipo='mora').count(), 1)

    def test_la_mora_usa_el_saldo_pendiente_no_el_total(self):
        self._vencido(self.u1, '100', 10)
        cobranza.registrar_recibo(usuario=self.user, unidad=self.u1, fecha=self.hoy, monto_pago='50')
        cobranza.aplicar_mora(self.hoy)
        self.assertEqual(Cargo.objects.get(tipo='mora').monto_usd, Decimal('1.00'))

    def test_no_hay_mora_sin_porcentaje_ni_dentro_de_la_gracia(self):
        self.edificio.mora_pct_mensual = Decimal('0')
        self.edificio.save()
        self._vencido(self.u1, '100', 10)
        self.assertEqual(cobranza.aplicar_mora(self.hoy), 0)

        self.edificio.mora_pct_mensual = Decimal('2')
        self.edificio.dias_gracia = 15
        self.edificio.save()
        self.assertEqual(cobranza.aplicar_mora(self.hoy), 0, 'vencida hace 10 días con 15 de gracia')

    def test_lo_pagado_o_no_vencido_no_genera_mora(self):
        cargo = self._vencido(self.u1, '100', 10)
        cobranza.registrar_recibo(usuario=self.user, unidad=self.u1, fecha=self.hoy, monto_pago='100')
        cobranza.crear_cargo(unidad=self.u2, tipo='cuota_condominio', concepto='Futura', periodo='2026-02', monto_usd='50', fecha_vencimiento=self.dias(5))
        self.assertEqual(cobranza.aplicar_mora(self.hoy), 0)
        cargo.refresh_from_db()
        self.assertEqual(cargo.estado, 'pagado')
