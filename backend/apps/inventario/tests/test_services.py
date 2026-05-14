from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase
from django.test import override_settings
from unittest.mock import patch
from ..models import Producto, Variacionproducto, Inventario, MovimientoInventario
from ..services.stock_service import reducir_stock_item, restaurar_stock_item, registrar_movimiento_manual

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
        self.inventario = Inventario.objects.create(producto=self.producto_simple, cantidad_disponible=20)

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
