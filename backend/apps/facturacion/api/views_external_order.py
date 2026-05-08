from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from apps.facturacion.services.external_order_service import create_external_order
import logging

logger = logging.getLogger(__name__)

class CreateExternalOrderCUD(APIView):
    """
    Endpoint público para que los clientes finales creen pedidos en la tienda del Tenant.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        cart_items = request.data.get('items', [])
        email_contacto = request.data.get('email', '')
        direccion = request.data.get('direccion', '')

        if not cart_items:
            return Response({"error": "El carrito está vacío"}, status=status.HTTP_400_BAD_REQUEST)

        # En django-tenants, el request.tenant nos da el Client actual
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({"error": "No se pudo identificar la tienda"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            orden = create_external_order(
                cart_items=cart_items,
                tenant=tenant,
                email_contacto=email_contacto,
                direccion=direccion
            )
            return Response({
                "message": "Pedido creado exitosamente",
                "orden_id": orden.id,
                "total": orden.total
            }, status=status.HTTP_201_CREATED)
        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creando orden externa: {str(e)}")
            return Response({"error": "Ocurrió un error al procesar el pedido"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
