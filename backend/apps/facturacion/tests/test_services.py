from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase
from django.test import override_settings
from unittest.mock import patch
from django.utils import timezone
from apps.facturacion.models import Factura, Detallefactura
from apps.inventario.models import Producto, Variacionproducto, Inventario
from apps.clientes.models import Cliente
from apps.configuracion.models import ConfiguracionCorrelativo
from apps.facturacion.services.order_service import crear_orden_desde_pedido_publico, OrderCreationError
from apps.facturacion.services.factura_service import anular_factura_y_restaurar_stock, FacturaAnulacionError

User = get_user_model()

# "Interceptamos" la llamada a la tarea de Celery para que no se ejecute durante los tests.
@patch('apps.inventario.services.stock_service.woocommerce_sync_task_celery.delay')
class FacturacionServiceTests(TenantTestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.cliente = Cliente.objects.create(nombre='Cliente Test', telefono='123456789')
        self.producto = Producto.objects.create(nombre='Producto Test')
        self.variacion = Variacionproducto.objects.create(producto=self.producto, sku='PT001', cantidad=10, precio=100)
        ConfiguracionCorrelativo.objects.create(pk=1, prefijo='F-', current_number=0, number_length=3)

    def test_crear_orden_desde_pedido_publico(self, mock_woocommerce_sync):
        validated_data = {
            'cliente_nombre': 'Nuevo Cliente',
            'cliente_telefono': '987654321',
            'items': [{'variacion_id': self.variacion.id, 'cantidad': 2}]
        }
        factura = crear_orden_desde_pedido_publico(validated_data, self.user)
        self.assertIsNotNone(factura)
        self.assertEqual(factura.estado, 'pendiente')
        self.assertEqual(factura.detalles.count(), 1)
        self.variacion.refresh_from_db()
        self.assertEqual(self.variacion.cantidad, 8) # Stock reducido
        mock_woocommerce_sync.assert_called_once() # Verificamos que la tarea se intentó llamar

    def test_crear_orden_stock_insuficiente(self, mock_woocommerce_sync):
        validated_data = {
            'cliente_nombre': 'Nuevo Cliente',
            'cliente_telefono': '987654321',
            'items': [{'variacion_id': self.variacion.id, 'cantidad': 15}] # Más de lo que hay
        }
        with self.assertRaises(OrderCreationError):
            crear_orden_desde_pedido_publico(validated_data, self.user)
        mock_woocommerce_sync.assert_not_called() # Verificamos que la tarea NO se llamó

    def test_anular_factura_y_restaurar_stock(self, mock_woocommerce_sync):
        factura = Factura.objects.create(
            cliente=self.cliente, 
            usuario=self.user, 
            correlativo='F-001', 
            estado='pagada',
            fecha_operacion=timezone.now(),
            subtotal=300,
            iva_total=0,
            total=300
        )
        # Asociamos el detalle con la variación específica que se vendió
        Detallefactura.objects.create(factura=factura, producto=self.producto, variante=self.variacion, cantidad=3, precio_unitario=100, subtotal_linea=300, total_linea=300)
        self.variacion.cantidad = 7 # Simular stock después de la venta
        self.variacion.save()
        
        anular_factura_y_restaurar_stock(factura.id)
        factura.refresh_from_db()
        self.assertEqual(factura.estado, 'anulada')
        self.variacion.refresh_from_db()
        self.assertEqual(self.variacion.cantidad, 10) # Stock restaurado
        mock_woocommerce_sync.assert_called_once() # Verificamos que la tarea se llamó

    def test_anular_factura_ya_anulada(self, mock_woocommerce_sync):
        factura = Factura.objects.create(
            cliente=self.cliente, 
            usuario=self.user, 
            correlativo='F-001', 
            estado='anulada',
            fecha_operacion=timezone.now(),
            subtotal=0,
            iva_total=0,
            total=0
        )
        with self.assertRaises(FacturaAnulacionError):
            anular_factura_y_restaurar_stock(factura.id)
        mock_woocommerce_sync.assert_not_called() # La tarea no debe llamarse si la anulación falla
