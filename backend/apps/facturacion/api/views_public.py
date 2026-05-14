from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema
from django.contrib.auth import get_user_model

from apps.inventario.models import Producto
from apps.configuracion.models import ConfiguracionEmpresa
from apps.core.whatsapp_service import WhatsAppService
from .serializers_public import PublicCreateOrderSerializer, PublicProductoSerializer
from apps.core.tasks import send_whatsapp_message_task
from ..services.order_service import crear_orden_desde_pedido_publico, OrderCreationError

class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10 # Puedes ajustar esto

class PublicProductCatalogView(APIView):
    """
    Vista pública para que los clientes vean el catálogo de productos.
    """
    permission_classes = [permissions.AllowAny]
    pagination_class = CustomPageNumberPagination

    @extend_schema(summary="Ver Catálogo de Productos Público", responses=PublicProductoSerializer(many=True))
    def get(self, request):
        productos_qs = Producto.objects.filter(activo=True, mostrar_en_catalogo=True).order_by('nombre')
        
        # Aplicar paginación
        page = self.paginate_queryset(productos_qs, request, view=self)
        serializer = PublicProductoSerializer(page, many=True, context={'request': request}) # Pasar request al serializer para imagen_url
        return self.pagination_class().get_paginated_response(serializer.data)

class PublicCreateOrderView(APIView):
    """
    Vista pública para que un cliente cree un nuevo pedido.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(summary="Crear un Nuevo Pedido desde el Catálogo", request=PublicCreateOrderSerializer)
    def post(self, request):
        serializer = PublicCreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Asumimos que existe un usuario "sistema" o el primer superusuario para asignar la orden
            usuario_sistema = get_user_model().objects.filter(is_superuser=True).first()
            if not usuario_sistema:
                return Response({"error": "No se pudo procesar el pedido. Falta configuración del sistema."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            factura = crear_orden_desde_pedido_publico(serializer.validated_data, usuario_sistema)
        except OrderCreationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Loggear el error real
            return Response({"error": "Ocurrió un error inesperado al procesar el pedido."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Notificar a la empresa por WhatsApp
        empresa_config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
        if empresa_config.telefono:
            cliente_nombre = serializer.validated_data['cliente_nombre']
            cliente_telefono = serializer.validated_data['cliente_telefono']
            
            # Mensaje para la empresa (enviado asíncronamente)
            send_whatsapp_message_task.delay(empresa_config.telefono, f"¡Nuevo pedido #{factura.correlativo} recibido de {cliente_nombre}! Revisa tu panel para ver los detalles.")

            # Mensaje para el cliente final (enviado asíncronamente)
            send_whatsapp_message_task.delay(cliente_telefono, f"¡Hola {cliente_nombre}! Tu pedido #{factura.correlativo} en {empresa_config.nombre_comercial} ha sido recibido. Te contactaremos pronto.")
            
        return Response({"message": "Pedido recibido exitosamente. Nos pondremos en contacto contigo."}, status=status.HTTP_201_CREATED)