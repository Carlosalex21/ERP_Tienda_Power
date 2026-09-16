from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from apps.core.testing import BaseTenantTestCase as TenantTestCase
from apps.inventario.models import Producto

from ..api.views import CatalogoPublicoView, CrearPedidoPublicoView

User = get_user_model()


class CatalogoPublicoViewTests(TenantTestCase):
    """
    Cubre la brecha que motivó consolidar este app: el catálogo público debe
    listar solo productos `disponible_online=True`, exponer el stock
    realmente vendible, y el pedido debe resolver por `producto_id` (no por
    `variacion_id`, que apuntaba a una tabla distinta -- ver order_service).
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        # CrearPedidoPublicoView atribuye el pedido al primer superusuario del tenant.
        User.objects.create_user(username='owner', password='x', is_superuser=True, is_staff=True)
        self.visible = Producto.objects.create(
            nombre='Visible', precio=Decimal('10.00'), cantidad=5,
            activo=True, disponible_online=True,
        )
        Producto.objects.create(
            nombre='Oculto', precio=Decimal('10.00'), cantidad=5,
            activo=True, disponible_online=False,
        )

    def test_catalogo_solo_lista_disponibles_online(self):
        request = self.factory.get('/api/v1/public/catalogo/')
        response = CatalogoPublicoView.as_view()(request)
        nombres = [p['nombre'] for p in response.data['results']]
        self.assertIn('Visible', nombres)
        self.assertNotIn('Oculto', nombres)

    def test_catalogo_expone_stock_disponible(self):
        request = self.factory.get('/api/v1/public/catalogo/')
        response = CatalogoPublicoView.as_view()(request)
        item = next(p for p in response.data['results'] if p['nombre'] == 'Visible')
        self.assertEqual(item['stock_disponible'], 5)

    def test_crear_pedido_resuelve_por_producto_id(self):
        payload = {
            'cliente_nombre': 'Cliente Test',
            'cliente_telefono': '04121234567',
            'items': [{'producto_id': self.visible.id, 'cantidad': 2}],
        }
        request = self.factory.post('/api/v1/public/ordenar/', payload, format='json')
        response = CrearPedidoPublicoView.as_view()(request)
        self.assertEqual(response.status_code, 201, response.data)
        self.visible.refresh_from_db()
        self.assertEqual(self.visible.cantidad, 3)

    def test_crear_pedido_con_producto_no_disponible_falla(self):
        oculto = Producto.objects.get(nombre='Oculto')
        payload = {
            'cliente_nombre': 'Cliente Test',
            'cliente_telefono': '04121234567',
            'items': [{'producto_id': oculto.id, 'cantidad': 1}],
        }
        request = self.factory.post('/api/v1/public/ordenar/', payload, format='json')
        response = CrearPedidoPublicoView.as_view()(request)
        self.assertEqual(response.status_code, 400)
