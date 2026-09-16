from django.contrib.auth import get_user_model
from apps.core.testing import BaseTenantTestCase as TenantTestCase
from django.test import override_settings
from unittest.mock import patch
from ..models import Producto, Variacionproducto, Inventario, MovimientoInventario, AjusteInventario
from ..services.stock_service import (
    reducir_stock_item, restaurar_stock_item, registrar_movimiento_manual, crear_y_aplicar_ajuste,
)

User = get_user_model()

@patch('apps.inventario.services.stock_service.woocommerce_sync_task_celery.delay')
class StockServiceTests(TenantTestCase):

    def setUp(self):
        """
        Crea los objetos necesarios para los tests de stock.
        """
        self.user = User.objects.create_user(username='testuser', password='password')
        self.producto_simple = Producto.objects.create(nombre='Producto Simple', cantidad=20)
        self.producto_con_variante = Producto.objects.create(nombre='Camisa')
        self.variante = Variacionproducto.objects.create(producto=self.producto_con_variante, nombre='Talla M', cantidad=15)
        self.inventario = Inventario.objects.create(producto=self.producto_simple, cantidad=20)

    def test_reducir_stock_producto_simple(self, mock_woocommerce_sync):
        """Prueba que se reduce el stock de un producto simple correctamente."""
        reducir_stock_item(self.producto_simple, 5)
        self.producto_simple.refresh_from_db()
        self.assertEqual(self.producto_simple.cantidad, 15)

    def test_reducir_stock_variacion(self, mock_woocommerce_sync):
        """Prueba que se reduce el stock de una variación correctamente."""
        reducir_stock_item(self.variante, 10)
        self.variante.refresh_from_db()
        self.assertEqual(self.variante.cantidad, 5)

    def test_reducir_stock_insuficiente_lanza_error(self, mock_woocommerce_sync):
        """Prueba que se lanza un ValueError si el stock es insuficiente."""
        with self.assertRaises(ValueError):
            reducir_stock_item(self.producto_simple, 25) # Intentar sacar más de lo que hay

    def test_restaurar_stock_producto_simple(self, mock_woocommerce_sync):
        """Prueba que se restaura el stock de un producto simple."""
        self.producto_simple.cantidad = 5
        self.producto_simple.save()
        restaurar_stock_item(self.producto_simple, 10)
        self.producto_simple.refresh_from_db()
        self.assertEqual(self.producto_simple.cantidad, 15)

    def test_restaurar_stock_variacion(self, mock_woocommerce_sync):
        """Prueba que se restaura el stock de una variación."""
        self.variante.cantidad = 2
        self.variante.save()
        restaurar_stock_item(self.variante, 8)
        self.variante.refresh_from_db()
        self.assertEqual(self.variante.cantidad, 10)

    def test_registrar_movimiento_manual_entrada(self, mock_woocommerce_sync):
        """Prueba un ingreso manual de stock y verifica el registro del movimiento."""
        registrar_movimiento_manual(self.inventario.id, 'entrada', 10, self.user)
        self.producto_simple.refresh_from_db()
        self.assertEqual(self.producto_simple.cantidad, 30)
        self.assertTrue(MovimientoInventario.objects.filter(inventario=self.inventario, tipo_movimiento='entrada').exists())

    def test_registrar_movimiento_manual_salida(self, mock_woocommerce_sync):
        """Prueba una salida manual de stock y verifica el registro del movimiento."""
        registrar_movimiento_manual(self.inventario.id, 'salida', 5, self.user)
        self.producto_simple.refresh_from_db()
        self.assertEqual(self.producto_simple.cantidad, 15)
        self.assertTrue(MovimientoInventario.objects.filter(inventario=self.inventario, tipo_movimiento='salida').exists())

    def test_crear_y_aplicar_ajuste_entrada_multilinea(self, mock_woocommerce_sync):
        """Un ajuste de entrada con varias líneas (producto simple + variante)
        debe sumar el stock de cada línea y dejar el ajuste con sus detalles."""
        otro_producto = Producto.objects.create(nombre='Producto Dos', cantidad=3)

        ajuste = crear_y_aplicar_ajuste(
            usuario=self.user,
            tipo='entrada',
            motivo='compra_sin_factura',
            numero_documento='NE-001',
            detalles_data=[
                {'producto': self.producto_simple, 'cantidad': 10},
                {'producto': otro_producto, 'cantidad': 4},
                {'producto': self.producto_con_variante, 'variante': self.variante, 'cantidad': 6},
            ],
        )

        self.producto_simple.refresh_from_db()
        otro_producto.refresh_from_db()
        self.variante.refresh_from_db()

        self.assertEqual(self.producto_simple.cantidad, 30)
        self.assertEqual(otro_producto.cantidad, 7)
        self.assertEqual(self.variante.cantidad, 21)
        self.assertEqual(ajuste.detalles.count(), 3)
        self.assertTrue(all(d.stock_resultante is not None for d in ajuste.detalles.all()))

    def test_crear_y_aplicar_ajuste_salida_insuficiente_no_deja_nada_a_medias(self, mock_woocommerce_sync):
        """Si una línea de salida no tiene stock suficiente, TODO el ajuste
        debe revertirse -- ninguna línea previa debe quedar aplicada."""
        otro_producto = Producto.objects.create(nombre='Producto Tres', cantidad=2)

        with self.assertRaises(ValueError):
            crear_y_aplicar_ajuste(
                usuario=self.user,
                tipo='salida',
                motivo='merma',
                detalles_data=[
                    {'producto': self.producto_simple, 'cantidad': 5},
                    {'producto': otro_producto, 'cantidad': 100},  # stock insuficiente
                ],
            )

        self.producto_simple.refresh_from_db()
        otro_producto.refresh_from_db()
        self.assertEqual(self.producto_simple.cantidad, 20, "la primera línea no debió quedar aplicada")
        self.assertEqual(otro_producto.cantidad, 2)
        self.assertEqual(AjusteInventario.objects.count(), 0, "no debió quedar un ajuste huérfano")
