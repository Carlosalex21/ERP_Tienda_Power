"""
Vistas públicas (sin autenticación) del catálogo y pedidos de un tenant.

Único punto de entrada `AllowAny` del sistema: si una vista nueva necesita
ser anónima, va aquí, no dentro de una app privada como `facturacion` o
`inventario`.
"""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.pagination import PageNumberPagination
from apps.core.throttling import ResilientScopedRateThrottle as ScopedRateThrottle
from drf_spectacular.utils import extend_schema

from apps.inventario.models import Producto
from apps.facturacion.models import Factura
from apps.configuracion.models import ConfiguracionEmpresa
from apps.core.tasks import send_whatsapp_message_task, dispatch_task
from apps.facturacion.services.order_service import crear_orden_desde_pedido_publico, OrderCreationError
from apps.pagos.models import MetodoPagoConfig
from apps.pagos.services.stripe_service import crear_checkout_session, procesar_webhook, StripeNoConfiguradoError

from apps.configuracion.services.conversion_service import obtener_tasas_actuales

from .serializers import (
    PublicCreateOrderSerializer,
    PublicProductoSerializer,
    PublicMetodoPagoConfigSerializer,
    PublicEmpresaInfoSerializer,
)

logger = logging.getLogger(__name__)


class CatalogoPageNumberPagination(PageNumberPagination):
    page_size = 10


class CatalogoPublicoView(generics.GenericAPIView):
    """
    Catálogo de productos visible para clientes finales anónimos.

    Hereda de ``GenericAPIView`` (no de ``APIView`` a secas): ``paginate_queryset``
    y ``get_paginated_response`` solo existen en ``GenericAPIView`` -- la
    implementación anterior los llamaba sobre un ``APIView`` plano, lo que
    hacía que este endpoint fallara con ``AttributeError`` en cada request.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'
    pagination_class = CatalogoPageNumberPagination
    serializer_class = PublicProductoSerializer

    def get_queryset(self):
        return Producto.objects.select_related('moneda', 'configuracion_iva').filter(
            activo=True, disponible_online=True,
        ).order_by('nombre')

    @extend_schema(summary="Ver Catálogo de Productos Público", responses=PublicProductoSerializer(many=True))
    def get(self, request):
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class MetodosPagoPublicoView(generics.ListAPIView):
    """Métodos de pago manuales (Pago Móvil/Zelle) activos, para mostrar en el checkout."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'
    serializer_class = PublicMetodoPagoConfigSerializer
    pagination_class = None

    def get_queryset(self):
        return MetodoPagoConfig.objects.filter(activo=True).order_by('nombre')


class EmpresaInfoPublicaView(APIView):
    """
    Nombre comercial y teléfono de contacto del tenant, para que el
    storefront pueda armar el enlace de WhatsApp con el número real del
    negocio -- antes estaba hardcodeado a un número de prueba fijo, igual
    para todos los tenants.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    def get(self, request):
        empresa, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
        serializer = PublicEmpresaInfoSerializer(empresa)
        return Response(serializer.data)


class TasasPublicasView(APIView):
    """
    Tasas de cambio vigentes de todas las monedas activas del tenant, sin
    autenticación -- para que el catálogo público muestre el precio también
    en otra moneda (ej. equivalente en USD de un precio en Bs), igual que ya
    se hace en el POS. Reutiliza el mismo servicio cacheado que usa el panel
    admin (`TasaCambioActualView`); esta es solo una versión `AllowAny`.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    def get(self, request):
        return Response(obtener_tasas_actuales())


class CrearPedidoPublicoView(APIView):
    """Permite a un cliente final crear un pedido desde el catálogo público."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    @extend_schema(summary="Crear un Nuevo Pedido desde el Catálogo", request=PublicCreateOrderSerializer)
    def post(self, request):
        serializer = PublicCreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Usuario "sistema" (primer superusuario) para atribuir pedidos
            # que no vienen de un usuario autenticado del panel.
            usuario_sistema = get_user_model().objects.filter(is_superuser=True).first()
            if not usuario_sistema:
                return Response({"error": "No se pudo procesar el pedido. Falta configuración del sistema."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            factura = crear_orden_desde_pedido_publico(serializer.validated_data, usuario_sistema)
        except OrderCreationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Ocurrió un error inesperado al procesar el pedido."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        empresa_config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
        if empresa_config.telefono:
            cliente_nombre = serializer.validated_data['cliente_nombre']
            cliente_telefono = serializer.validated_data['cliente_telefono']

            dispatch_task(send_whatsapp_message_task, empresa_config.telefono, f"¡Nuevo pedido #{factura.correlativo} recibido de {cliente_nombre}! Revisa tu panel para ver los detalles.")
            dispatch_task(send_whatsapp_message_task, cliente_telefono, f"¡Hola {cliente_nombre}! Tu pedido #{factura.correlativo} en {empresa_config.nombre_comercial} ha sido recibido. Te contactaremos pronto.")

        return Response({
            "message": "Pedido recibido exitosamente. Nos pondremos en contacto contigo.",
            "factura_id": factura.id,
            "correlativo": factura.correlativo,
        }, status=status.HTTP_201_CREATED)


class CrearSesionStripeView(APIView):
    """
    Crea una Stripe Checkout Session para un pedido ya creado (ver
    ``CrearPedidoPublicoView``) y devuelve la URL a la que redirigir al
    cliente para pagar con tarjeta en moneda extranjera.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    def post(self, request):
        factura_id = request.data.get('factura_id')
        success_url = request.data.get('success_url')
        cancel_url = request.data.get('cancel_url')
        if not (factura_id and success_url and cancel_url):
            return Response(
                {"error": "Se requieren factura_id, success_url y cancel_url."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        factura = Factura.objects.filter(id=factura_id, estado='pendiente').first()
        if not factura:
            return Response({"error": "Pedido no encontrado o ya procesado."}, status=status.HTTP_404_NOT_FOUND)

        try:
            checkout_url = crear_checkout_session(factura, success_url, cancel_url)
        except StripeNoConfiguradoError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {"error": "No se pudo iniciar el pago con tarjeta. Intenta con otro método."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"checkout_url": checkout_url}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """
    Endpoint que Stripe llama directamente (no un navegador) para avisar que
    un pago se completó. La firma (`Stripe-Signature`) prueba que la
    petición realmente viene de Stripe -- sin verificarla, cualquiera podría
    llamar esta URL y marcar pedidos como pagados sin haber pagado nada.
    Exento de CSRF (no es un navegador el que llama) como cualquier webhook
    externo.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        try:
            procesar_webhook(request.body, sig_header)
        except StripeNoConfiguradoError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.warning("Webhook de Stripe rechazado: %s", e)
            return Response({"error": "Firma inválida."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_200_OK)
