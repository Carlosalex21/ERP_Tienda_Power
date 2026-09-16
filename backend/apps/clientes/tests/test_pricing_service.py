from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.testing import BaseTenantTestCase as TenantTestCase
from apps.inventario.models import Producto

from ..models import ClienteB2B, NivelPrecio
from ..services.pricing_service import calcular_precio_efectivo
from ..services.b2b_order_service import crear_pedido_b2b, B2BOrderCreationError
from ..api.views_b2b import B2BCatalogoView, B2BCrearPedidoView

User = get_user_model()


class PricingServiceTests(TenantTestCase):
    """
    `NivelPrecio.porcentaje_descuento` se guardaba desde el onboarding B2B
    pero, antes de `pricing_service`, ningún endpoint lo aplicaba sobre un
    precio real -- estos tests cubren que ahora sí lo hace.
    """

    def setUp(self):
        self.producto = Producto.objects.create(nombre='Producto B2B', precio=Decimal('100.00'), cantidad=50, disponible_online=True, activo=True)
        self.nivel = NivelPrecio.objects.create(nombre='Mayorista', porcentaje_descuento=Decimal('15.00'))

    def test_sin_cliente_b2b_devuelve_precio_de_lista(self):
        self.assertEqual(calcular_precio_efectivo(self.producto, None), Decimal('100.00'))

    def test_con_cliente_b2b_aplica_descuento_del_nivel(self):
        cliente = ClienteB2B(nivel_precio=self.nivel)  # sin persistir: no hace falta guardarlo para este cálculo
        self.assertEqual(calcular_precio_efectivo(self.producto, cliente), Decimal('85.00'))


class B2BCatalogoViewTests(TenantTestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.nivel = NivelPrecio.objects.create(nombre='VIP', porcentaje_descuento=Decimal('20.00'))
        self.user = User.objects.create_user(username='b2b-user', password='x')
        self.cliente_b2b = ClienteB2B.objects.create(
            user=self.user,
            razon_social='Comercial Test C.A.',
            rif='J-12345678-9',
            email_contacto='compras@comercialtest.com',
            nivel_precio=self.nivel,
            estado='activo',
        )
        self.producto = Producto.objects.create(nombre='Producto B2B', precio=Decimal('100.00'), cantidad=10, disponible_online=True, activo=True)

    def test_catalogo_b2b_devuelve_precio_con_descuento(self):
        request = self.factory.get('/api/v1/clientes/b2b/catalogo/')
        force_authenticate(request, user=self.user)
        response = B2BCatalogoView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        item = next(p for p in response.data['results'] if p['nombre'] == 'Producto B2B')
        self.assertEqual(Decimal(item['precio_lista']), Decimal('100.00'))
        self.assertEqual(Decimal(item['precio_con_descuento']), Decimal('80.00'))

    def test_usuario_sin_perfil_b2b_recibe_403(self):
        otro_user = User.objects.create_user(username='sin-b2b', password='x')
        request = self.factory.get('/api/v1/clientes/b2b/catalogo/')
        force_authenticate(request, user=otro_user)
        response = B2BCatalogoView.as_view()(request)
        self.assertEqual(response.status_code, 403)


class B2BOrderServiceTests(TenantTestCase):
    """
    Antes de `b2b_order_service`, un cliente B2B podía ver su precio con
    descuento pero no existía ningún endpoint para comprar -- estos tests
    cubren que el pedido se cobra al precio efectivo, no al de lista.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.nivel = NivelPrecio.objects.create(nombre='Mayorista', porcentaje_descuento=Decimal('10.00'))
        self.user = User.objects.create_user(username='b2b-comprador', password='x')
        self.cliente_b2b = ClienteB2B.objects.create(
            user=self.user,
            razon_social='Compradora B2B C.A.',
            rif='J-98765432-1',
            email_contacto='pedidos@compradorab2b.com',
            nivel_precio=self.nivel,
            estado='activo',
        )
        self.producto = Producto.objects.create(nombre='Producto Mayorista', precio=Decimal('50.00'), cantidad=20, disponible_online=True, activo=True)

    def test_crear_pedido_b2b_cobra_precio_con_descuento_y_reduce_stock(self):
        factura = crear_pedido_b2b(self.cliente_b2b, [{'producto_id': self.producto.id, 'cantidad': 3}])
        detalle = factura.detalles.get()
        self.assertEqual(detalle.precio_unitario, Decimal('45.00'))  # 50 - 10%
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.cantidad, 17)

    def test_crear_pedido_b2b_producto_inexistente_falla(self):
        with self.assertRaises(B2BOrderCreationError):
            crear_pedido_b2b(self.cliente_b2b, [{'producto_id': 999999, 'cantidad': 1}])

    def test_endpoint_crear_pedido_b2b(self):
        payload = {'items': [{'producto_id': self.producto.id, 'cantidad': 2}]}
        request = self.factory.post('/api/v1/clientes/b2b/pedidos/', payload, format='json')
        force_authenticate(request, user=self.user)
        response = B2BCrearPedidoView.as_view()(request)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn('correlativo', response.data)
