"""Morosidad, estado de cuenta, tablero, portal del condómino y PDFs."""
from decimal import Decimal

from apps.inmuebles.models import Cargo, MedioPago, PagoReportado, Recibo
from apps.inmuebles.services import cobranza, pdf, portal, reportes
from apps.inmuebles.services.cobranza import CobranzaError

from .base import InmueblesBase


class ReportesTests(InmueblesBase):

    def _cargo(self, unidad, monto, dias_vencido, periodo='2026-01'):
        return cobranza.crear_cargo(
            unidad=unidad, tipo='cuota_condominio', concepto=f'Cuota {periodo}', periodo=periodo, monto_usd=monto,
            fecha_vencimiento=self.dias(-dias_vencido), fecha_emision=self.dias(-dias_vencido - 30),
        )

    def test_morosidad_por_tramos_y_porcentaje(self):
        self._cargo(self.u1, '100', 10, '2026-08')
        self._cargo(self.u1, '50', 70, '2026-06')
        self._cargo(self.u2, '30', 120, '2026-04')
        self._cargo(self.u3, '20', -5, '2026-10')  # aún no vence
        r = reportes.reporte_morosidad(fecha_corte=self.hoy)
        self.assertEqual(r['resumen']['unidades_morosas'], 2)
        self.assertEqual(r['resumen']['total_unidades'], 3)
        self.assertEqual(r['resumen']['porcentaje_morosidad'], '66.67')
        self.assertEqual(r['resumen']['total_vencido_usd'], '180.00')
        primera = r['filas'][0]
        self.assertEqual((primera['unidad'], primera['total_vencido_usd'], primera['0_30'], primera['61_90'], primera['meses_vencidos']), ('A-1', '150.00', '100.00', '50.00', 2))
        self.assertEqual(r['filas'][1]['mas_90'], '30.00')

    def test_morosidad_por_edificio_y_recordatorios(self):
        from apps.inmuebles.models import Unidad

        self._cargo(self.u1, '100', 10)
        sin_dueno = Unidad.objects.create(edificio=self.edificio, codigo='B-1', alicuota=0)
        self._cargo(sin_dueno, '40', 10)
        reporte = reportes.reporte_morosidad()
        self.assertEqual(reporte['resumen']['unidades_morosas'], 2)
        self.assertEqual(len(reportes.recordatorios_morosidad()), 1, 'solo A-1 tiene responsable con teléfono')
        self.assertEqual(reportes.reporte_morosidad(edificio_id=999)['resumen']['unidades_morosas'], 0)

    def test_estado_de_cuenta_con_saldo_acumulado(self):
        self._cargo(self.u1, '100', 20, '2026-08')
        cobranza.registrar_recibo(usuario=self.user, unidad=self.u1, fecha=self.hoy, monto_pago='40')
        e = reportes.estado_cuenta(self.u1)
        self.assertEqual([m['tipo'] for m in e['movimientos']], ['cargo', 'pago'])
        self.assertEqual(e['movimientos'][-1]['saldo'], '60.00')
        self.assertEqual((e['saldo_usd'], e['vencido_usd']), ('60.00', '60.00'))

    def test_solvencia(self):
        self.assertTrue(reportes.estado_solvencia(self.u1)['solvente'])
        self._cargo(self.u1, '10', 3)
        estado = reportes.estado_solvencia(self.u1)
        self.assertFalse(estado['solvente'])
        self.assertEqual(estado['vencido_usd'], Decimal('10.00'))

    def test_tablero(self):
        self._cargo(self.u1, '100', 10)
        cobranza.registrar_recibo(usuario=self.user, unidad=self.u2, fecha=self.hoy, monto_pago='25')
        m = reportes.metricas_tablero()
        self.assertEqual(m['cartera_vencida_usd'], '100.00')
        self.assertEqual(m['cobrado_mes_usd'], '25.00')
        self.assertEqual(m['unidades_total'], 3)
        self.assertEqual(m['pagos_por_revisar'], 0)


class PortalTests(InmueblesBase):

    def setUp(self):
        super().setUp()
        self.cuota = cobranza.crear_cargo(
            unidad=self.u1, tipo='cuota_condominio', concepto='Cuota 2026-09', periodo='2026-09', monto_usd='100',
            fecha_vencimiento=self.dias(-3), fecha_emision=self.dias(-30),
        )
        MedioPago.objects.create(edificio=self.edificio, tipo='pago_movil', banco='Banesco', numero_cuenta='0414-1112233', titular='Condominio', moneda='VES')
        MedioPago.objects.create(edificio=None, tipo='zelle', numero_cuenta='admin@x.com', moneda='USD')
        self.acceso = portal.obtener_o_crear_acceso(self.ana)

    def _reportar(self, **kw):
        datos = dict(unidad_id=self.u1.pk, fecha_pago=self.hoy, monto_pago='4000', moneda_pago='VES', metodo='pago_movil', referencia='123456')
        datos.update(kw)
        return portal.reportar_pago(self.acceso, **datos)

    def test_accesos_se_crean_regeneran_y_revocan(self):
        self.assertEqual(portal.obtener_o_crear_acceso(self.ana).pk, self.acceso.pk)
        nuevo = portal.regenerar_acceso(self.ana)
        self.assertNotEqual(nuevo.token, self.acceso.token)
        self.assertIsNone(portal.acceso_por_token(self.acceso.token))
        self.assertEqual(portal.acceso_por_token(nuevo.token).cliente, self.ana)
        portal.revocar_accesos(self.ana)
        self.assertIsNone(portal.acceso_por_token(nuevo.token))
        self.assertIsNone(portal.acceso_por_token('inventado'))

    def test_datos_del_portal(self):
        d = portal.datos_portal(self.acceso)
        self.assertEqual(d['persona']['nombre'], 'Ana Pérez')
        self.assertEqual((d['saldo_total_usd'], d['vencido_total_usd']), ('100.00', '100.00'))
        unidad = d['unidades'][0]
        self.assertEqual((unidad['codigo'], unidad['rol']), ('A-1', 'propietario'))
        self.assertEqual(len(unidad['cargos']), 1)
        self.assertTrue(unidad['cargos'][0]['vencido'])
        self.assertEqual({m['tipo'] for m in unidad['medios_pago']}, {'pago_movil', 'zelle'})
        self.assertIsNone(unidad['morosidad_edificio'])
        self.assertEqual(d['tasa']['moneda'], 'VES')

    def test_el_portal_solo_muestra_lo_de_esa_persona(self):
        otro = portal.obtener_o_crear_acceso(self.luis)
        d = portal.datos_portal(otro)
        self.assertEqual([u['codigo'] for u in d['unidades']], ['A-2'])

    def test_morosidad_del_edificio_solo_con_codigos_si_esta_activada(self):
        self.edificio.portal_muestra_morosidad = True
        self.edificio.save()
        m = portal.datos_portal(self.acceso)['unidades'][0]['morosidad_edificio']
        self.assertEqual(m['unidades'], [{'codigo': 'A-1', 'meses_vencidos': 1}])
        self.assertNotIn('Ana', str(m))

    def test_reportar_y_aprobar_un_pago_genera_el_recibo(self):
        pago = self._reportar(cargos_ids=[self.cuota.pk])
        self.assertEqual(pago.estado, 'pendiente')
        aprobado = portal.aprobar_pago_reportado(pago, usuario=self.user, tasa=Decimal('40'))
        self.cuota.refresh_from_db()
        self.assertEqual(aprobado.estado, 'aprobado')
        self.assertEqual(aprobado.recibo.monto_usd, Decimal('100.00'))  # 4000 / 40
        self.assertEqual(self.cuota.estado, 'pagado')
        with self.assertRaises(CobranzaError):
            portal.aprobar_pago_reportado(aprobado, usuario=self.user)

    def test_rechazar_exige_motivo_y_no_toca_las_deudas(self):
        pago = self._reportar()
        with self.assertRaises(CobranzaError):
            portal.rechazar_pago_reportado(pago, usuario=self.user, motivo=' ')
        rechazado = portal.rechazar_pago_reportado(pago, usuario=self.user, motivo='No aparece en el banco')
        self.cuota.refresh_from_db()
        self.assertEqual((rechazado.estado, self.cuota.monto_pagado_usd), ('rechazado', Decimal('0.00')))
        self.assertEqual(Recibo.objects.count(), 0)

    def test_validaciones_del_aviso_de_pago(self):
        casos = [
            dict(unidad_id=self.u2.pk),                 # unidad ajena
            dict(monto_pago='0'),
            dict(fecha_pago=self.dias(1)),              # futura
            dict(fecha_pago=self.dias(-500)),           # muy vieja
            dict(moneda_pago='EUR'),
            dict(referencia=''),                        # pago móvil sin referencia
            dict(cargos_ids=[99999]),
        ]
        for caso in casos:
            with self.subTest(caso=caso), self.assertRaises(CobranzaError):
                self._reportar(**caso)
        self.assertEqual(PagoReportado.objects.count(), 0)

    def test_no_se_reporta_dos_veces_la_misma_referencia(self):
        self._reportar()
        with self.assertRaises(CobranzaError):
            self._reportar()

    def test_limite_de_avisos_pendientes_por_unidad(self):
        for i in range(portal.MAX_PENDIENTES_POR_UNIDAD):
            self._reportar(referencia=f'R{i}')
        with self.assertRaises(CobranzaError):
            self._reportar(referencia='una-mas')


class PdfTests(InmueblesBase):

    def test_todos_los_pdf_se_generan(self):
        from apps.inmuebles.models import GastoComun
        from apps.inmuebles.services import condominio

        GastoComun.objects.create(edificio=self.edificio, periodo='2026-10', categoria='agua', descripcion='Agua', monto_usd='200', fecha=self.hoy)
        periodo = condominio.emitir_periodo(self.edificio, '2026-10', usuario=self.user)
        cuota = Cargo.objects.get(periodo_condominio=periodo, unidad=self.u1)
        recibo = cobranza.registrar_recibo(usuario=self.user, unidad=self.u1, fecha=self.hoy, monto_pago='50')
        for nombre, datos in (
            ('recibo', pdf.pdf_recibo(recibo)), ('estado_cuenta', pdf.pdf_estado_cuenta(self.u1)), ('solvencia', pdf.pdf_solvencia(self.u1)),
            ('recibo_condominio', pdf.pdf_recibo_condominio(cuota)),
        ):
            with self.subTest(nombre):
                self.assertTrue(datos.startswith(b'%PDF'), nombre)
