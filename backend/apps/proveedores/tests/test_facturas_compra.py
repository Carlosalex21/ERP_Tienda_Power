"""
Flujos de dinero de Compras: factura de compra -> inventario, costo,
cuenta por pagar, Libro de Compras, retención de IVA y anulación.
"""
import re
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model

from apps.core.testing import BaseTenantTestCase as TenantTestCase
from apps.configuracion.models import ConfiguracionCorrelativo
from apps.facturacion.models import LibroCompraVenta, Retencion
from apps.facturacion.services.retencion_service import (
    anular_comprobante_retencion, crear_comprobante_retencion,
)
from apps.inventario.api.serializers_ajustes import error_motivo_ajuste
from apps.inventario.models import Almacen, Inventario, Producto
from apps.proveedores.core.compras_service import crear_orden_compra, enviar_orden_compra
from apps.proveedores.core.facturas_compra_service import (
    FacturaCompraError, anular_factura_compra, registrar_factura_compra,
)
from apps.proveedores.models import CuentaPorPagar, Proveedor

User = get_user_model()


@patch('apps.inventario.services.stock_service.woocommerce_sync_task_celery.delay')
class FacturaCompraTests(TenantTestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='compras', password='x')
        self.proveedor = Proveedor.objects.create(
            identificador_fiscal='J123456789', nombre='Distribuidora XYZ', direccion='Caracas',
            email='xyz@example.com', plazo_pago=30,
        )
        self.almacen = Almacen.objects.create(nombre='Principal', direccion='Caracas')
        self.producto = Producto.objects.create(nombre='Harina', cantidad=10, costo_promedio=Decimal('1.00'))
        ConfiguracionCorrelativo.objects.get_or_create(pk=1)

    def _registrar(self, **kwargs):
        datos = dict(
            usuario=self.user, proveedor=self.proveedor, tipo_documento='factura',
            numero_factura='000123', numero_control='00-000456', fecha_emision=date(2026, 9, 15),
            almacen=self.almacen,
            detalles=[{'producto': self.producto, 'cantidad': 10, 'costo_unitario': Decimal('2.00')}],
            porcentaje_iva=Decimal('16'),
        )
        datos.update(kwargs)
        return registrar_factura_compra(**datos)

    def test_factura_mueve_stock_costo_cxp_y_libro(self, _):
        factura = self._registrar()

        self.assertEqual(factura.base_imponible, Decimal('20.00'))
        self.assertEqual(factura.iva, Decimal('3.20'))
        self.assertEqual(factura.total, Decimal('23.20'))

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad, 20)
        # (10 x 1.00 + 10 x 2.00) / 20 -- el costo es SIN IVA.
        self.assertEqual(self.producto.costo_promedio.quantize(Decimal('0.01')), Decimal('1.50'))
        self.assertEqual(Inventario.objects.get(producto=self.producto, almacen=self.almacen).cantidad, 10)

        cuenta = CuentaPorPagar.objects.get(factura_compra=factura)
        self.assertEqual(cuenta.monto, Decimal('23.20'))
        self.assertEqual(cuenta.fecha_vencimiento, date(2026, 10, 15))

        linea = LibroCompraVenta.objects.get(factura_compra=factura)
        self.assertEqual(linea.tipo_libro, 'compra')
        self.assertEqual(linea.rif, 'J123456789')
        self.assertEqual(linea.iva, Decimal('3.20'))

    def test_exento_se_descuenta_de_la_base(self, _):
        factura = self._registrar(monto_exento=Decimal('5.00'))
        self.assertEqual(factura.base_imponible, Decimal('15.00'))
        self.assertEqual(factura.iva, Decimal('2.40'))
        self.assertEqual(factura.total, Decimal('22.40'))

    def test_retencion_iva_75_sobre_el_impuesto_y_rebaja_la_deuda(self, _):
        factura = self._registrar(porcentaje_retencion_iva=Decimal('75'))

        retencion = Retencion.objects.get(factura_compra=factura)
        self.assertEqual(retencion.base, Decimal('3.20'))
        self.assertEqual(retencion.monto, Decimal('2.40'))
        self.assertEqual(retencion.proveedor, self.proveedor)
        # Formato SENIAT: AAAAMM + secuencial de 8 dígitos.
        self.assertRegex(retencion.numero_comprobante, r'^\d{6}00000001$')

        factura.refresh_from_db()
        self.assertEqual(factura.retencion_iva, Decimal('2.40'))
        self.assertEqual(CuentaPorPagar.objects.get(factura_compra=factura).monto, Decimal('20.80'))
        self.assertEqual(LibroCompraVenta.objects.get(factura_compra=factura).retencion, Decimal('2.40'))

        anular_comprobante_retencion(retencion)
        self.assertEqual(CuentaPorPagar.objects.get(factura_compra=factura).monto, Decimal('23.20'))

    def test_retencion_no_consume_numero_de_control_de_ventas(self, _):
        config = ConfiguracionCorrelativo.objects.get(pk=1)
        control_antes = config.current_control_number
        r1 = crear_comprobante_retencion(proveedor=self.proveedor, tipo_retencion='iva', porcentaje=Decimal('75'), base=Decimal('10'))
        r2 = crear_comprobante_retencion(proveedor=self.proveedor, tipo_retencion='islr', porcentaje=Decimal('2'), base=Decimal('100'))
        r3 = crear_comprobante_retencion(proveedor=self.proveedor, tipo_retencion='iva', porcentaje=Decimal('75'), base=Decimal('10'))
        config.refresh_from_db()
        self.assertEqual(config.current_control_number, control_antes)
        self.assertTrue(r1.numero_comprobante.endswith('00000001'))
        self.assertTrue(r2.numero_comprobante.endswith('00000001'))
        self.assertTrue(r3.numero_comprobante.endswith('00000002'))
        self.assertTrue(all(re.fullmatch(r'\d{14}', r.numero_comprobante) for r in (r1, r2, r3)))

    def test_nota_de_entrega_no_va_al_libro_ni_lleva_iva(self, _):
        factura = self._registrar(tipo_documento='nota_entrega', numero_control='', porcentaje_retencion_iva=Decimal('75'))
        self.assertEqual(factura.iva, Decimal('0.00'))
        self.assertFalse(LibroCompraVenta.objects.filter(factura_compra=factura).exists())
        self.assertFalse(Retencion.objects.filter(factura_compra=factura).exists())
        self.assertEqual(CuentaPorPagar.objects.get(factura_compra=factura).monto, Decimal('20.00'))

    def test_factura_fiscal_exige_numero_de_control(self, _):
        with self.assertRaises(FacturaCompraError):
            self._registrar(numero_control='')

    def test_misma_factura_dos_veces_se_rechaza(self, _):
        self._registrar()
        with self.assertRaises(FacturaCompraError):
            self._registrar()

    def test_desde_orden_de_compra_actualiza_lo_recibido(self, _):
        orden = crear_orden_compra(
            proveedor_id=self.proveedor.pk, usuario=self.user, almacen_id=self.almacen.pk,
            detalles_data=[{'producto_id': self.producto.pk, 'cantidad': 15}],
        )
        enviar_orden_compra(orden)
        detalle_oc = orden.detalles.get()

        self._registrar(orden_compra=orden, detalles=[{
            'producto': self.producto, 'cantidad': 10, 'costo_unitario': Decimal('2.00'), 'orden_detalle_id': detalle_oc.pk,
        }])
        orden.refresh_from_db()
        detalle_oc.refresh_from_db()
        self.assertEqual(detalle_oc.cantidad_recibida, 10)
        self.assertEqual(orden.estado, 'recibida_parcial')

        with self.assertRaises(FacturaCompraError):
            self._registrar(numero_factura='000124', orden_compra=orden, detalles=[{
                'producto': self.producto, 'cantidad': 6, 'costo_unitario': Decimal('2.00'), 'orden_detalle_id': detalle_oc.pk,
            }])

    def test_anular_revierte_todo(self, _):
        factura = self._registrar(porcentaje_retencion_iva=Decimal('100'))
        anular_factura_compra(factura, usuario=self.user)

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad, 10)
        self.assertEqual(CuentaPorPagar.objects.get(factura_compra=factura).estado, 'anulada')
        self.assertFalse(LibroCompraVenta.objects.get(factura_compra=factura).activo)
        self.assertFalse(Retencion.objects.filter(factura_compra=factura, activo=True).exists())
        # Anulada, el mismo número se puede volver a cargar bien.
        self._registrar()

    def test_ajuste_no_admite_compras_ni_motivos_incoherentes(self, _):
        self.assertIsNotNone(error_motivo_ajuste('compra_con_factura', 'entrada'))
        self.assertIsNotNone(error_motivo_ajuste('merma', 'entrada'))
        self.assertIsNotNone(error_motivo_ajuste('inventario_inicial', 'salida'))
        self.assertIsNone(error_motivo_ajuste('conteo_fisico', 'entrada'))
        self.assertIsNone(error_motivo_ajuste('consumo_interno', 'salida'))
