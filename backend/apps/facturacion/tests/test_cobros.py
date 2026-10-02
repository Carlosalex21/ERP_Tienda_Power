"""
Cobro de ventas (`procesar_pago_factura_service`): pago completo, dividido,
con vuelto, a crédito con abonos y rechazos. Es el flujo que mueve el dinero
del negocio todos los días.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.testing import BaseTenantTestCase as TenantTestCase
from apps.facturacion.models import Detallefactura, Factura, MetodoPago, Transaccionpago
from apps.facturacion.services.pagos_service import calcular_saldo_pendiente, procesar_pago_factura_service
from apps.inventario.models import Producto

User = get_user_model()


@patch('apps.inventario.services.stock_service.woocommerce_sync_task_celery.delay')
class CobroDeVentasTests(TenantTestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='cajero', password='x')
        self.producto = Producto.objects.create(nombre='Harina', cantidad=10, precio=Decimal('50.00'))
        self.efectivo = MetodoPago.objects.create(nombre='Efectivo')
        self.transferencia = MetodoPago.objects.create(nombre='Transferencia')
        self.factura = Factura.objects.create(
            usuario=self.user, estado='abierta', fecha_operacion=timezone.now(),
            subtotal=Decimal('100.00'), iva_total=Decimal('0.00'), total=Decimal('100.00'),
        )
        Detallefactura.objects.create(
            factura=self.factura, producto=self.producto, cantidad=2,
            precio_unitario=Decimal('50.00'), subtotal_linea=Decimal('100.00'), total_linea=Decimal('100.00'),
        )

    def _cobrar(self, pagos, **kwargs):
        return procesar_pago_factura_service(self.factura.id, pagos, kwargs.get('estado_override'), kwargs.get('datos', {}), usuario=self.user)

    def test_pago_completo_cierra_la_factura_y_descuenta_el_stock(self, _):
        factura, transacciones = self._cobrar([{'metodo_pago_id': self.efectivo.id, 'monto': Decimal('100.00')}])
        self.assertEqual(factura.estado, 'pagado')
        self.assertEqual(len(transacciones), 1)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad, 8)
        self.assertEqual(calcular_saldo_pendiente(factura), Decimal('0.00'))

    def test_el_vuelto_queda_registrado(self, _):
        _, transacciones = self._cobrar([{'metodo_pago_id': self.efectivo.id, 'monto': Decimal('100.00'), 'monto_recibido': Decimal('120.00')}])
        self.assertEqual(transacciones[0].vuelto, Decimal('20.00'))
        self.assertEqual(transacciones[0].monto, Decimal('100.00'))

    def test_recibir_menos_de_lo_cobrado_se_corrige_al_monto(self, _):
        _, transacciones = self._cobrar([{'metodo_pago_id': self.efectivo.id, 'monto': Decimal('100.00'), 'monto_recibido': Decimal('80.00')}])
        self.assertEqual(transacciones[0].vuelto, Decimal('0.00'))

    def test_pago_dividido_en_dos_metodos(self, _):
        factura, transacciones = self._cobrar([
            {'metodo_pago_id': self.efectivo.id, 'monto': Decimal('60.00')},
            {'metodo_pago_id': self.transferencia.id, 'monto': Decimal('40.00'), 'referencia': 'REF123'},
        ])
        self.assertEqual(factura.estado, 'pagado')
        self.assertEqual(len(transacciones), 2)
        self.assertEqual(transacciones[1].referencia, 'REF123')

    def test_abonos_a_credito_hasta_saldar_sin_descontar_dos_veces_el_stock(self, _):
        factura, _t = self._cobrar([{'metodo_pago_id': self.efectivo.id, 'monto': Decimal('40.00')}])
        self.assertEqual(factura.estado, 'pendiente')
        self.assertEqual(factura.condicion_pago, 'credito')
        self.assertEqual(calcular_saldo_pendiente(factura), Decimal('60.00'))

        factura, _t = self._cobrar([{'metodo_pago_id': self.efectivo.id, 'monto': Decimal('60.00')}])
        self.assertEqual(factura.estado, 'pagado')
        self.assertEqual(calcular_saldo_pendiente(factura), Decimal('0.00'))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad, 8, 'el stock se descuenta una sola vez')
        self.assertEqual(Transaccionpago.objects.filter(factura=factura).count(), 2)

    def test_pagar_luego_deja_la_cuenta_pendiente_sin_dinero(self, _):
        factura, transacciones = self._cobrar([], estado_override='pendiente', datos={'nombre_cliente': 'Pedro'})
        self.assertEqual(factura.estado, 'pendiente')
        self.assertEqual(transacciones, [])
        self.assertEqual(factura.nombre_cliente_pendiente, 'Pedro')
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad, 8, 'la mercancía ya salió')

    def test_pagos_invalidos_se_rechazan_sin_tocar_nada(self, _):
        with self.assertRaises(ValueError):
            self._cobrar([])
        with self.assertRaises(ValueError):
            self._cobrar([{'metodo_pago_id': 99999, 'monto': Decimal('10.00')}])
        with self.assertRaises(ValueError):
            self._cobrar([{'metodo_pago_id': self.efectivo.id, 'monto': Decimal('0')}])
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'abierta')
        self.assertFalse(Transaccionpago.objects.exists())

    def test_una_factura_ya_pagada_no_se_cobra_otra_vez(self, _):
        self._cobrar([{'metodo_pago_id': self.efectivo.id, 'monto': Decimal('100.00')}])
        with self.assertRaises(ValueError):
            self._cobrar([{'metodo_pago_id': self.efectivo.id, 'monto': Decimal('100.00')}])
        self.assertEqual(Transaccionpago.objects.filter(factura=self.factura).count(), 1)
