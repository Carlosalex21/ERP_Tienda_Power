"""La API completa: rutas, permisos, formato de errores, catálogo público y portal."""
import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from PIL import Image
from rest_framework.test import APIClient

from apps.inmuebles.models import Cargo, ConsultaPropiedad, Contrato, GastoComun, PagoReportado, Recibo, Unidad
from apps.inmuebles.services import cobranza, portal
from apps.usuarios.models import Rol, UserMetadata

from .base import InmueblesBase

User = get_user_model()
BASE = '/api/v1/inmuebles'


def png(nombre='comprobante.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), 'blue').save(buffer, 'PNG')
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type='image/png')


class ApiBase(InmueblesBase):

    def setUp(self):
        super().setUp()
        rol_admin = Rol.objects.create(nombre='Administrador', codigo='admin')
        rol_vendedor = Rol.objects.create(nombre='Vendedor', codigo='vendedor')
        rol_almacen = Rol.objects.create(nombre='Almacenista', codigo='almacenista')
        UserMetadata.objects.create(user=self.user, rol=rol_admin)
        self.vendedor = User.objects.create_user(username='vendedor_inm', password='x')
        UserMetadata.objects.create(user=self.vendedor, rol=rol_vendedor)
        self.otro = User.objects.create_user(username='almacen_inm', password='x')
        UserMetadata.objects.create(user=self.otro, rol=rol_almacen)

        host = self.get_test_tenant_domain()
        self.api = self._cliente(host, self.user)
        self.api_vendedor = self._cliente(host, self.vendedor)
        self.api_sin_permiso = self._cliente(host, self.otro)
        self.publico = APIClient(HTTP_HOST=host)

    @staticmethod
    def _cliente(host, usuario):
        cliente = APIClient(HTTP_HOST=host)
        cliente.force_authenticate(usuario)
        return cliente

    def datos(self, respuesta):
        return respuesta.json()['data']

    def errores(self, respuesta):
        return respuesta.json()['errors']


class PanelApiTests(ApiBase):

    def test_endpoints_exigen_ser_personal(self):
        self.assertEqual(self.api_sin_permiso.get(f'{BASE}/unidades/').status_code, 403)
        self.assertEqual(APIClient(HTTP_HOST=self.get_test_tenant_domain()).get(f'{BASE}/unidades/').status_code, 401)
        self.assertEqual(self.api_vendedor.get(f'{BASE}/unidades/').status_code, 200)

    def test_unidades_y_propiedades_son_el_mismo_recurso(self):
        r = self.api.post(f'{BASE}/propiedades/', {'codigo': 'Casa 1', 'tipo': 'casa', 'edificio': None, 'alicuota': 0}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        codigos = [u['codigo'] for u in self.datos(self.api.get(f'{BASE}/unidades/'))]
        self.assertIn('Casa 1', codigos)

    def test_codigo_de_unidad_duplicado_da_un_error_legible(self):
        r = self.api.post(f'{BASE}/unidades/', {'edificio': self.edificio.pk, 'codigo': 'a-1', 'alicuota': 1}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Ya existe una unidad', self.errores(r)[0]['detail'])
        self.assertEqual(self.errores(r)[0]['field'], 'codigo')

    def test_publicar_exige_operacion_y_precio(self):
        r = self.api.patch(f'{BASE}/unidades/{self.u1.pk}/', {'publicada': True}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.patch(f'{BASE}/unidades/{self.u1.pk}/', {'publicada': True, 'operacion': 'venta', 'precio_venta_usd': '90000'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)

    def test_no_se_desactiva_una_unidad_con_deuda_ni_un_edificio_con_unidades(self):
        cobranza.crear_cargo(unidad=self.u1, tipo='cuota_condominio', concepto='C', periodo='2026-10', monto_usd='10', fecha_vencimiento=self.dias(5))
        self.assertEqual(self.api.delete(f'{BASE}/unidades/{self.u1.pk}/').status_code, 400)
        self.assertEqual(self.api.delete(f'{BASE}/edificios/{self.edificio.pk}/').status_code, 400)
        self.assertEqual(self.api.delete(f'{BASE}/unidades/{self.u2.pk}/').status_code, 204)
        self.u2.refresh_from_db()
        self.assertFalse(self.u2.activo)

    def test_flujo_de_condominio_gastos_emitir_cobrar(self):
        periodo = '2026-10'
        r = self.api.post(f'{BASE}/gastos-comunes/', {'edificio': self.edificio.pk, 'periodo': periodo, 'categoria': 'agua', 'descripcion': 'Agua', 'monto_usd': '1000', 'fecha': str(self.hoy)}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        vista = self.datos(self.api.get(f'{BASE}/periodos-condominio/previsualizar/', {'edificio': self.edificio.pk, 'periodo': periodo}))
        self.assertEqual(vista['total_a_distribuir_usd'], '1100.00')
        self.assertEqual(self.api_vendedor.post(f'{BASE}/periodos-condominio/emitir/', {'edificio': self.edificio.pk, 'periodo': periodo}, format='json').status_code, 403)
        r = self.api.post(f'{BASE}/periodos-condominio/emitir/', {'edificio': self.edificio.pk, 'periodo': periodo}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.datos(r)['cuotas'], 3)

        # Ya emitido: no admite gastos nuevos, y el mensaje llega legible.
        r = self.api.post(f'{BASE}/gastos-comunes/', {'edificio': self.edificio.pk, 'periodo': periodo, 'categoria': 'aseo', 'descripcion': 'x', 'monto_usd': '5', 'fecha': str(self.hoy)}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ya fue emitido', self.errores(r)[0]['detail'])

        cuota = Cargo.objects.get(unidad=self.u1, periodo=periodo)
        r = self.api_vendedor.post(f'{BASE}/recibos/', {'unidad': self.u1.pk, 'fecha': str(self.hoy), 'monto_pago': '2000', 'moneda_pago': 'VES', 'tasa': '40', 'metodo': 'pago_movil', 'referencia': 'ABC123'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        recibo = self.datos(r)
        self.assertEqual(recibo['monto_usd'], '50.00')
        self.assertEqual(len(recibo['aplicaciones']), 1)
        cuota.refresh_from_db()
        self.assertEqual(cuota.monto_pagado_usd, Decimal('50.00'))

        pdf = self.api.get(f"{BASE}/recibos/{recibo['id']}/pdf/")
        self.assertEqual((pdf.status_code, pdf['Content-Type']), (200, 'application/pdf'))
        self.assertTrue(self.api.get(f'{BASE}/cargos/{cuota.pk}/recibo-condominio-pdf/').content.startswith(b'%PDF'))

        self.assertEqual(self.api_vendedor.post(f"{BASE}/recibos/{recibo['id']}/anular/", {}, format='json').status_code, 403)
        self.assertEqual(self.api.post(f"{BASE}/recibos/{recibo['id']}/anular/", {'motivo': 'prueba'}, format='json').status_code, 200)

    def test_error_de_negocio_llega_en_el_formato_estandar(self):
        r = self.api.post(f'{BASE}/recibos/', {'unidad': self.u1.pk, 'fecha': str(self.dias(3)), 'monto_pago': '10'}, format='json')
        self.assertEqual(r.status_code, 400)
        error = self.errores(r)[0]
        self.assertEqual(error['detail'], 'La fecha del pago no puede ser futura.')
        self.assertIsNone(error['field'])

    def test_cargo_manual_y_su_anulacion(self):
        r = self.api.post(f'{BASE}/cargos/', {'unidad': self.u1.pk, 'tipo': 'extraordinaria', 'concepto': 'Reparación de ascensor', 'periodo': '2026-10', 'monto_usd': '75', 'fecha_vencimiento': str(self.dias(15))}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        cargo_id = self.datos(r)['id']
        self.assertEqual(self.api.post(f'{BASE}/cargos/{cargo_id}/anular/', {}, format='json').status_code, 200)
        self.assertEqual(self.api.post(f'{BASE}/cargos/{cargo_id}/anular/', {}, format='json').status_code, 400)

    def test_foto_invalida_se_rechaza_y_valida_se_guarda(self):
        malo = SimpleUploadedFile('virus.png', b'<script>alert(1)</script>', content_type='image/png')
        self.assertEqual(self.api.post(f'{BASE}/propiedades/{self.u1.pk}/fotos/', {'imagen': malo}, format='multipart').status_code, 400)
        ok = self.api.post(f'{BASE}/propiedades/{self.u1.pk}/fotos/', {'imagen': png('casa.png')}, format='multipart')
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertTrue(self.datos(ok)['es_portada'])
        self.assertEqual(self.api.delete(f"{BASE}/propiedades/{self.u1.pk}/fotos/{self.datos(ok)['id']}/").status_code, 204)

    def test_importar_unidades_desde_csv(self):
        contenido = (
            'codigo,tipo,alicuota,area_m2,propietario_nombre,propietario_documento,propietario_telefono,propietario_email\n'
            'B-1,apartamento,2.5,80,María Gil,V-111,0414-5550001,maria@x.com\n'
            'B-2,Local,3,40,María Gil,V-111,,\n'
            'A-1,apartamento,1,50,Repetida,V-999,,\n'
            ',apartamento,1,50,Sin código,,,\n'
            'B-3,casa,150,50,Alícuota mala,,,\n'
        )
        archivo = SimpleUploadedFile('u.csv', contenido.encode('utf-8'), content_type='text/csv')
        r = self.api.post(f'{BASE}/unidades/importar/', {'archivo': archivo, 'edificio': self.edificio.pk}, format='multipart')
        self.assertEqual(r.status_code, 200, r.content)
        resumen = self.datos(r)
        self.assertEqual((resumen['creadas'], resumen['con_error']), (2, 3))
        self.assertEqual(Unidad.objects.get(codigo='B-1').propietario, Unidad.objects.get(codigo='B-2').propietario)
        self.assertEqual(Unidad.objects.get(codigo='B-2').tipo, 'local')
        self.assertTrue(self.api.get(f'{BASE}/unidades/plantilla-csv/').content.startswith(b'codigo,'))
        malo = SimpleUploadedFile('u.txt', b'x', content_type='text/plain')
        self.assertEqual(self.api.post(f'{BASE}/unidades/importar/', {'archivo': malo}, format='multipart').status_code, 400)

    def test_reportes(self):
        cobranza.crear_cargo(unidad=self.u1, tipo='cuota_condominio', concepto='C', periodo='2026-08', monto_usd='100', fecha_vencimiento=self.dias(-40), fecha_emision=self.dias(-70))
        morosidad = self.datos(self.api.get(f'{BASE}/reportes/morosidad/'))
        self.assertEqual(morosidad['resumen']['unidades_morosas'], 1)
        self.assertEqual(len(self.datos(self.api.get(f'{BASE}/reportes/recordatorios/'))), 1)
        self.assertEqual(self.datos(self.api.get(f'{BASE}/reportes/tablero/'))['cartera_vencida_usd'], '100.00')
        self.assertEqual(self.api.get(f'{BASE}/reportes/morosidad/', {'fecha_corte': 'mañana'}).status_code, 400)
        self.assertTrue(self.api.get(f'{BASE}/unidades/{self.u1.pk}/solvencia-pdf/').content.startswith(b'%PDF'))
        self.assertTrue(self.api.get(f'{BASE}/unidades/{self.u1.pk}/estado-cuenta-pdf/').content.startswith(b'%PDF'))

    def test_las_alertas_incluyen_morosidad_y_pagos_por_revisar(self):
        from apps.reportes.core.alertas_service import obtener_alertas

        cobranza.crear_cargo(unidad=self.u1, tipo='cuota_condominio', concepto='C', periodo='2026-06', monto_usd='100', fecha_vencimiento=self.dias(-80), fecha_emision=self.dias(-110))
        acceso = portal.obtener_o_crear_acceso(self.ana)
        portal.reportar_pago(acceso, unidad_id=self.u1.pk, fecha_pago=self.hoy, monto_pago='10', moneda_pago='USD', metodo='efectivo')
        tipos = {a['tipo'] for a in obtener_alertas()['alertas']}
        self.assertTrue({'morosidad', 'pagos_reportados'} <= tipos)


class AlquileresApiTests(ApiBase):

    def setUp(self):
        super().setUp()
        self.casa = self.unidad('Casa 5', Decimal('0'), self.ana, edificio=None, estado='disponible')

    def _contrato(self):
        return self.api.post(f'{BASE}/contratos/', {
            'unidad': self.casa.pk, 'inquilino': self.luis.pk, 'fecha_inicio': str(self.hoy), 'fecha_fin': str(self.dias(365)),
            'canon_usd': '400', 'dia_pago': 5, 'deposito_usd': '0', 'honorario_pct': '10',
        }, format='json')

    def test_contrato_crear_activar_cobrar_liquidar_y_rescindir(self):
        r = self._contrato()
        self.assertEqual(r.status_code, 201, r.content)
        cid = self.datos(r)['id']
        self.assertEqual(self.datos(r)['estado'], 'borrador')
        r = self.api.post(f'{BASE}/contratos/{cid}/activar/', {}, format='json')
        self.assertEqual((r.status_code, self.datos(r)['estado']), (200, 'vigente'))
        self.assertEqual(self.api.patch(f'{BASE}/contratos/{cid}/', {'canon_usd': '1'}, format='json').status_code, 400)

        r = self.api.post(f'{BASE}/recibos/', {'unidad': self.casa.pk, 'fecha': str(self.hoy), 'monto_pago': '400', 'metodo': 'efectivo'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)

        vista = self.datos(self.api.get(f'{BASE}/liquidaciones/previsualizar/', {'propietario': self.ana.pk}))
        self.assertEqual((vista['total_cobrado_usd'], vista['honorario_usd'], vista['neto_usd']), ('400.00', '40.00', '360.00'))
        self.assertEqual(self.api_vendedor.post(f'{BASE}/liquidaciones/generar/', {'propietario': self.ana.pk}, format='json').status_code, 403)
        r = self.api.post(f'{BASE}/liquidaciones/generar/', {'propietario': self.ana.pk}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        lid = self.datos(r)['id']
        self.assertTrue(self.api.get(f'{BASE}/liquidaciones/{lid}/pdf/').content.startswith(b'%PDF'))
        self.assertEqual(self.api.post(f'{BASE}/liquidaciones/{lid}/pagar/', {'referencia': 'TRF1'}, format='json').status_code, 200)

        r = self.api.post(f'{BASE}/contratos/{cid}/rescindir/', {'motivo': 'Fin de mutuo acuerdo'}, format='json')
        self.assertEqual((r.status_code, self.datos(r)['estado']), (200, 'rescindido'))

    def test_renovar_y_filtro_por_vencer(self):
        cid = self.datos(self._contrato())['id']
        self.api.post(f'{BASE}/contratos/{cid}/activar/', {}, format='json')
        self.assertEqual(len(self.datos(self.api.get(f'{BASE}/contratos/', {'por_vencer': 400}))), 1)
        self.assertEqual(len(self.datos(self.api.get(f'{BASE}/contratos/', {'por_vencer': 30}))), 0)
        r = self.api.post(f'{BASE}/contratos/{cid}/renovar/', {'nueva_fecha_fin': str(self.dias(730)), 'nuevo_canon': '450'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.datos(r)['canon_usd'], '450.00')

    def test_solo_un_borrador_se_elimina(self):
        cid = self.datos(self._contrato())['id']
        self.api.post(f'{BASE}/contratos/{cid}/activar/', {}, format='json')
        self.assertEqual(self.api.delete(f'{BASE}/contratos/{cid}/').status_code, 400)


class PublicoApiTests(ApiBase):

    def setUp(self):
        super().setUp()
        self.casa = self.unidad(
            'Casa Sol', Decimal('0'), self.ana, edificio=None, operacion='alquiler_venta', publicada=True, titulo='Casa luminosa',
            zona='Los Palos Grandes', ciudad='Caracas', direccion='Av. Secreta 123', canon_usd='600', precio_venta_usd='90000',
            habitaciones=3, banos=2, amenidades=['Piscina', 'Vigilancia'], tipo='casa',
        )
        self.oculta = self.unidad('Casa Oculta', Decimal('0'), self.ana, edificio=None, operacion='venta', publicada=False, precio_venta_usd='1')
        self.sin_oferta = self.unidad('Casa Privada', Decimal('0'), self.ana, edificio=None, operacion='ninguna', publicada=True)

    def test_el_catalogo_solo_muestra_lo_publicado_sin_datos_privados(self):
        r = self.publico.get(f'{BASE}/publico/propiedades/')
        self.assertEqual(r.status_code, 200)
        items = self.datos(r)
        self.assertEqual([i['titulo_visible'] for i in items], ['Casa luminosa'])
        texto = r.content.decode()
        self.assertNotIn('Av. Secreta', texto)
        self.assertNotIn('Ana', texto)
        self.assertEqual(r.json()['meta']['pagination']['count'], 1)

    def test_filtros(self):
        self.unidad('Apto Barato', Decimal('0'), self.luis, edificio=None, operacion='alquiler', publicada=True, canon_usd='200', habitaciones=1, tipo='apartamento', zona='Chacao')
        pedir = lambda **q: [i['titulo_visible'] for i in self.datos(self.publico.get(f'{BASE}/publico/propiedades/', q))]  # noqa: E731
        self.assertEqual(len(pedir()), 2)
        self.assertEqual(pedir(operacion='venta'), ['Casa luminosa'])
        self.assertEqual(len(pedir(operacion='alquiler')), 2)
        self.assertEqual(pedir(operacion='alquiler', precio_max='300'), ['Apartamento en Chacao'])
        self.assertEqual(pedir(habitaciones='3'), ['Casa luminosa'])
        self.assertEqual(pedir(zona='chacao'), ['Apartamento en Chacao'])
        self.assertEqual(pedir(q='luminosa'), ['Casa luminosa'])
        self.assertEqual(pedir(operacion='alquiler', orden='precio_asc')[0], 'Apartamento en Chacao')
        self.assertEqual(self.publico.get(f'{BASE}/publico/propiedades/', {'precio_min': 'abc'}).status_code, 400)

    def test_detalle_y_facetas(self):
        d = self.publico.get(f'{BASE}/publico/propiedades/{self.casa.pk}/')
        self.assertEqual(d.status_code, 200)
        self.assertEqual(self.datos(d)['amenidades'], ['Piscina', 'Vigilancia'])
        self.assertEqual(self.publico.get(f'{BASE}/publico/propiedades/{self.oculta.pk}/').status_code, 404)
        f = self.datos(self.publico.get(f'{BASE}/publico/propiedades/filtros/'))
        self.assertEqual((f['zonas'], f['hay_alquiler'], f['hay_venta']), (['Los Palos Grandes'], True, True))

    def test_consulta_publica(self):
        datos = {'unidad': self.casa.pk, 'nombre': 'Pedro Interesado', 'telefono': '0412-9998877', 'mensaje': '¿Sigue disponible?'}
        self.assertEqual(self.publico.post(f'{BASE}/publico/consultas/', datos, format='json').status_code, 201)
        self.assertEqual(ConsultaPropiedad.objects.count(), 1)
        self.publico.post(f'{BASE}/publico/consultas/', datos, format='json')  # doble clic
        self.assertEqual(ConsultaPropiedad.objects.count(), 1)
        self.publico.post(f'{BASE}/publico/consultas/', {**datos, 'telefono': '0412-1112233', 'sitio_web': 'http://spam'}, format='json')
        self.assertEqual(ConsultaPropiedad.objects.count(), 1, 'el señuelo anti-bots no guarda nada')
        self.assertEqual(self.publico.post(f'{BASE}/publico/consultas/', {'nombre': 'A', 'telefono': '1'}, format='json').status_code, 400)
        self.assertEqual(self.publico.post(f'{BASE}/publico/consultas/', {**datos, 'unidad': self.oculta.pk, 'telefono': '0412-5556677'}, format='json').status_code, 404)

        consulta = ConsultaPropiedad.objects.get()
        r = self.api.patch(f'{BASE}/consultas/{consulta.pk}/', {'estado': 'contactada', 'notas': 'Llamé'}, format='json')
        self.assertEqual((r.status_code, self.datos(r)['estado']), (200, 'contactada'))
        self.assertEqual(self.api.patch(f'{BASE}/consultas/{consulta.pk}/', {'nombre': 'Hackeado'}, format='json').json()['data']['nombre'], 'Pedro Interesado')


class PortalApiTests(ApiBase):

    def setUp(self):
        super().setUp()
        self.cuota = cobranza.crear_cargo(
            unidad=self.u1, tipo='cuota_condominio', concepto='Cuota 2026-09', periodo='2026-09', monto_usd='100',
            fecha_vencimiento=self.dias(-3), fecha_emision=self.dias(-30),
        )
        self.token = portal.obtener_o_crear_acceso(self.ana).token

    def url(self, ruta=''):
        return f'{BASE}/portal/{self.token}/{ruta}'

    def test_enlace_invalido_o_revocado(self):
        self.assertEqual(self.publico.get(f'{BASE}/portal/no-existe/').status_code, 404)
        self.assertEqual(self.publico.get(self.url()).status_code, 200)
        portal.revocar_accesos(self.ana)
        self.assertEqual(self.publico.get(self.url()).status_code, 404)

    def test_datos_del_portal(self):
        d = self.datos(self.publico.get(self.url()))
        self.assertEqual((d['persona']['nombre'], d['saldo_total_usd']), ('Ana Pérez', '100.00'))
        self.assertEqual(d['unidades'][0]['cargos'][0]['concepto'], 'Cuota 2026-09')

    def test_el_condomino_avisa_su_pago_y_la_administracion_lo_aprueba(self):
        formulario = {
            'unidad': self.u1.pk, 'fecha_pago': str(self.hoy), 'monto_pago': '4000', 'moneda_pago': 'VES', 'metodo': 'pago_movil',
            'referencia': '778899', 'banco': 'Banesco', 'cargos': [self.cuota.pk], 'comprobante': png(),
        }
        r = self.publico.post(self.url('reportar-pago/'), formulario, format='multipart')
        self.assertEqual(r.status_code, 201, r.content)
        pago = PagoReportado.objects.get()
        self.assertEqual((pago.estado, list(pago.cargos.all())), ('pendiente', [self.cuota]))
        self.assertTrue(pago.comprobante.name.startswith('inmuebles/comprobantes/'))

        r = self.api.post(f'{BASE}/pagos-reportados/{pago.pk}/aprobar/', {'tasa': '40'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.datos(r)['estado'], 'aprobado')
        self.cuota.refresh_from_db()
        self.assertEqual(self.cuota.estado, 'pagado')

        d = self.datos(self.publico.get(self.url()))
        self.assertEqual(d['saldo_total_usd'], '0.00')
        recibo = Recibo.objects.get()
        pdf = self.publico.get(self.url(f'recibo/{recibo.pk}/pdf/'))
        self.assertEqual((pdf.status_code, pdf['Content-Type']), (200, 'application/pdf'))

    def test_comprobante_malicioso_y_datos_invalidos_se_rechazan(self):
        base = {'unidad': self.u1.pk, 'fecha_pago': str(self.hoy), 'monto_pago': '10', 'moneda_pago': 'USD', 'metodo': 'efectivo'}
        malo = SimpleUploadedFile('comprobante.html', b'<script>alert(1)</script>')
        self.assertEqual(self.publico.post(self.url('reportar-pago/'), {**base, 'comprobante': malo}, format='multipart').status_code, 400)
        self.assertEqual(self.publico.post(self.url('reportar-pago/'), {**base, 'monto_pago': 'abc'}, format='multipart').status_code, 400)
        self.assertEqual(self.publico.post(self.url('reportar-pago/'), {**base, 'unidad': self.u2.pk}, format='multipart').status_code, 400)
        self.assertEqual(PagoReportado.objects.count(), 0)

    def test_no_se_ven_documentos_de_otra_persona(self):
        ajeno = cobranza.registrar_recibo(usuario=self.user, unidad=self.u2, fecha=self.hoy, monto_pago='5')
        self.assertEqual(self.publico.get(self.url(f'recibo/{ajeno.pk}/pdf/')).status_code, 404)
        self.assertEqual(self.publico.get(self.url(f'unidad/{self.u2.pk}/estado-cuenta/pdf/')).status_code, 404)
        self.assertEqual(self.publico.get(self.url(f'unidad/{self.u1.pk}/estado-cuenta/pdf/')).status_code, 200)

    def test_generar_y_revocar_el_enlace_desde_el_panel(self):
        r = self.api.post(f'{BASE}/portal-accesos/', {'cliente': self.luis.pk}, format='json')
        token = self.datos(r)['token']
        self.assertEqual(self.api.post(f'{BASE}/portal-accesos/', {'cliente': self.luis.pk}, format='json').json()['data']['token'], token)
        nuevo = self.datos(self.api.post(f'{BASE}/portal-accesos/', {'cliente': self.luis.pk, 'regenerar': True}, format='json'))['token']
        self.assertNotEqual(nuevo, token)
        self.assertEqual(self.publico.get(f'{BASE}/portal/{token}/').status_code, 404)
        self.assertEqual(self.datos(self.api.delete(f'{BASE}/portal-accesos/', {'cliente': self.luis.pk}, format='json'))['revocados'], 1)

    def test_cuota_de_condominio_en_pdf_desde_el_portal(self):
        from apps.inmuebles.services import condominio

        GastoComun.objects.create(edificio=self.edificio, periodo='2026-10', categoria='agua', descripcion='Agua', monto_usd='100', fecha=self.hoy)
        periodo = condominio.emitir_periodo(self.edificio, '2026-10', usuario=self.user)
        cuota = periodo.cargos.get(unidad=self.u1)
        self.assertEqual(self.publico.get(self.url(f'cuota/{cuota.pk}/pdf/')).status_code, 200)
        self.assertEqual(self.publico.get(self.url(f'cuota/{periodo.cargos.get(unidad=self.u2).pk}/pdf/')).status_code, 404)
        self.assertEqual(Contrato.objects.count(), 0)
