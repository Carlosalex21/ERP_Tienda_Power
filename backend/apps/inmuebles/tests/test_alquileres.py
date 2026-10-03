"""Inmobiliaria: contratos, cánones mensuales y liquidación al propietario."""
from datetime import timedelta
from decimal import Decimal

from apps.inmuebles.models import Cargo, Contrato, GastoPropiedad, Liquidacion, Recibo
from apps.inmuebles.services import cobranza, contratos, liquidaciones
from apps.inmuebles.services.cobranza import CobranzaError

from .base import InmueblesBase


class AlquilerBase(InmueblesBase):

    def setUp(self):
        super().setUp()
        self.casa = self.unidad('Casa 12', Decimal('0'), self.ana, edificio=None, estado='disponible', operacion='alquiler', publicada=True)
        self.inquilino = self.luis

    def contrato(self, **kw):
        datos = dict(
            usuario=self.user, unidad=self.casa, inquilino=self.inquilino, fecha_inicio=self.dias(-5), fecha_fin=self.dias(360),
            canon_usd='500', dia_pago=5, deposito_usd='500', honorario_pct='10',
        )
        datos.update(kw)
        return contratos.crear_contrato(**datos)


class ContratosTests(AlquilerBase):

    def test_activar_ocupa_la_propiedad_y_genera_deposito_y_primer_canon(self):
        c = contratos.activar_contrato(self.contrato())
        self.casa.refresh_from_db()
        self.assertEqual(c.estado, 'vigente')
        self.assertEqual((self.casa.estado, self.casa.ocupante, self.casa.publicada), ('ocupada', self.inquilino, False))
        self.assertEqual(Cargo.objects.filter(contrato=c, tipo='canon').count(), 1)
        self.assertEqual(Cargo.objects.get(tipo='deposito').monto_usd, Decimal('500.00'))
        self.assertEqual(c.propietario, self.ana)

    def test_generar_cargos_es_idempotente(self):
        c = contratos.activar_contrato(self.contrato())
        self.assertEqual(contratos.generar_cargos_contrato(c), 0)
        self.assertEqual(Cargo.objects.filter(contrato=c, tipo='canon').count(), 1)

    def test_se_generan_los_meses_que_faltan_hasta_el_mes_pedido(self):
        c = contratos.activar_contrato(self.contrato(fecha_inicio=self.hoy))
        futuro = cobranza.sumar_meses(cobranza.periodo_de(self.hoy), 2)
        self.assertEqual(contratos.generar_cargos_contrato(c, hasta_periodo=futuro), 2)
        self.assertEqual(Cargo.objects.filter(contrato=c, tipo='canon').count(), 3)

    def test_dos_contratos_vigentes_no_pueden_solaparse(self):
        contratos.activar_contrato(self.contrato())
        otro = self.contrato(inquilino=self.eva, fecha_inicio=self.dias(100))
        with self.assertRaises(CobranzaError):
            contratos.activar_contrato(otro)

    def test_fechas_y_canon_validos(self):
        with self.assertRaises(CobranzaError):
            self.contrato(fecha_inicio=self.dias(10), fecha_fin=self.dias(10))
        with self.assertRaises(CobranzaError):
            self.contrato(canon_usd='0')

    def test_ajuste_anual_del_canon(self):
        c = self.contrato(fecha_inicio=self.hoy.replace(year=self.hoy.year - 2), fecha_fin=self.dias(300), ajuste_anual_pct='10')
        periodo_hoy = cobranza.periodo_de(self.hoy)
        self.assertEqual(contratos.canon_del_periodo(c, cobranza.periodo_de(c.fecha_inicio)), Decimal('500.00'))
        self.assertEqual(contratos.canon_del_periodo(c, periodo_hoy), Decimal('605.00'))  # 500 * 1.1^2

    def test_rescindir_libera_la_propiedad_y_anula_lo_futuro(self):
        c = contratos.activar_contrato(self.contrato(fecha_inicio=self.hoy))
        siguiente = cobranza.sumar_meses(cobranza.periodo_de(self.hoy), 1)
        contratos.generar_cargos_contrato(c, hasta_periodo=siguiente)
        contratos.rescindir_contrato(c, fecha=self.hoy, motivo='Mudanza')
        self.casa.refresh_from_db()
        self.assertEqual((self.casa.estado, self.casa.ocupante), ('disponible', None))
        self.assertEqual(Cargo.objects.get(contrato=c, periodo=siguiente).estado, 'anulado')
        self.assertEqual(Cargo.objects.get(contrato=c, periodo=cobranza.periodo_de(self.hoy)).estado, 'pendiente')

    def test_renovar_crea_el_contrato_siguiente(self):
        c = contratos.activar_contrato(self.contrato())
        nuevo = contratos.renovar_contrato(c, usuario=self.user, nueva_fecha_fin=self.dias(720), nuevo_canon='550')
        self.assertEqual(nuevo.fecha_inicio, c.fecha_fin + timedelta(days=1))
        self.assertEqual((nuevo.estado, nuevo.canon_usd, nuevo.contrato_anterior), ('vigente', Decimal('550.00'), c))
        self.assertEqual(Cargo.objects.filter(tipo='deposito').count(), 1, 'la renovación no vuelve a cobrar el depósito')

    def test_procesar_contratos_vence_los_terminados(self):
        c = contratos.activar_contrato(self.contrato(fecha_inicio=self.dias(-30), fecha_fin=self.dias(10)))
        resumen = contratos.procesar_contratos(self.dias(11))
        c.refresh_from_db()
        self.assertEqual(resumen['vencidos'], 1)
        self.assertEqual(c.estado, 'vencido')


class LiquidacionTests(AlquilerBase):

    def setUp(self):
        super().setUp()
        self.c = contratos.activar_contrato(self.contrato(deposito_usd='0'))
        self.canon = Cargo.objects.get(contrato=self.c, tipo='canon')

    def _cobrar(self, monto='500'):
        return cobranza.registrar_recibo(usuario=self.user, unidad=self.casa, fecha=self.hoy, monto_pago=monto, referencia=f'R{monto}')

    def test_neto_es_cobrado_menos_honorario_menos_gastos(self):
        self._cobrar('500')
        GastoPropiedad.objects.create(unidad=self.casa, fecha=self.hoy, descripcion='Reparación de tubería', monto_usd='80')
        vista = liquidaciones.previsualizar_liquidacion(self.ana)
        self.assertEqual((vista['total_cobrado_usd'], vista['honorario_usd'], vista['gastos_usd'], vista['neto_usd']), ('500.00', '50.00', '80.00', '370.00'))
        liq = liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        self.assertEqual((liq.estado, liq.neto_usd), ('borrador', Decimal('370.00')))
        self.assertEqual(liq.lineas.count(), 3)

    def test_lo_liquidado_no_se_liquida_dos_veces(self):
        self._cobrar('500')
        liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        with self.assertRaises(CobranzaError):
            liquidaciones.generar_liquidacion(self.ana, usuario=self.user)

    def test_sin_cobros_ni_gastos_no_hay_nada_que_liquidar(self):
        with self.assertRaises(CobranzaError):
            liquidaciones.generar_liquidacion(self.ana, usuario=self.user)

    def test_el_deposito_no_entra_en_la_liquidacion(self):
        otro = self.unidad('Casa 13', Decimal('0'), self.ana, edificio=None)
        c2 = contratos.activar_contrato(self.contrato(unidad=otro, inquilino=self.eva, deposito_usd='300'))
        cobranza.registrar_recibo(usuario=self.user, unidad=otro, fecha=self.hoy, monto_pago='300', cargos=[Cargo.objects.get(tipo='deposito')])
        with self.assertRaises(CobranzaError):
            liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        self.assertIsNotNone(c2.pk)

    def test_anular_la_liquidacion_libera_los_cobros(self):
        recibo = self._cobrar('500')
        liq = liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        with self.assertRaises(CobranzaError):
            cobranza.anular_recibo(recibo)  # ya está en una liquidación
        liquidaciones.anular_liquidacion(liq)
        nueva = liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        self.assertEqual(nueva.total_cobrado_usd, Decimal('500.00'))
        self.assertEqual(Liquidacion.objects.exclude(estado='anulada').count(), 1)

    def test_una_liquidacion_pagada_no_se_anula(self):
        self._cobrar('500')
        liq = liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        liquidaciones.pagar_liquidacion(liq, referencia='TRF-99')
        with self.assertRaises(CobranzaError):
            liquidaciones.anular_liquidacion(liq)
        with self.assertRaises(CobranzaError):
            liquidaciones.pagar_liquidacion(liq)

    def test_pagos_parciales_se_liquidan_por_lo_realmente_cobrado(self):
        self._cobrar('200')
        liq = liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        self.assertEqual((liq.total_cobrado_usd, liq.honorario_usd, liq.neto_usd), (Decimal('200.00'), Decimal('20.00'), Decimal('180.00')))
        self._cobrar('300')
        liq2 = liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        self.assertEqual(liq2.total_cobrado_usd, Decimal('300.00'))

    def test_recibos_anulados_no_se_liquidan(self):
        recibo = self._cobrar('500')
        cobranza.anular_recibo(recibo)
        with self.assertRaises(CobranzaError):
            liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        self.assertEqual(Recibo.objects.filter(estado='anulado').count(), 1)
        self.assertEqual(Contrato.objects.count(), 1)

    def test_pdf_de_la_liquidacion(self):
        from apps.inmuebles.services import pdf

        self._cobrar('500')
        liq = liquidaciones.generar_liquidacion(self.ana, usuario=self.user)
        self.assertTrue(pdf.pdf_liquidacion(liq).startswith(b'%PDF'))
