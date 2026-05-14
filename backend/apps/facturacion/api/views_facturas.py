from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from ..models import Factura
from .serializers import FacturaSerializer
from apps.core.permissions import IsTenantAdmin, IsAdminOrVendedor
from ..services.factura_service import anular_factura_y_restaurar_stock, FacturaAnulacionError

class FacturaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para la gestión completa de Facturas (Listar, Crear, Obtener, Actualizar, Eliminar).
    """
    queryset = Factura.objects.select_related('cliente', 'usuario', 'metodo_pago').prefetch_related('detalles__producto')
    serializer_class = FacturaSerializer
    
    def get_permissions(self):
        """
        Asigna permisos basados en la acción.
        """
        if self.action in ['list', 'retrieve', 'create', 'update', 'partial_update']:
            # Vendedores y Admins pueden ver, crear y editar facturas.
            self.permission_classes = [IsAdminOrVendedor]
        elif self.action == 'destroy':
            # Solo Admins pueden borrar facturas.
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()

class AnularFacturaView(APIView):
    permission_classes = [IsTenantAdmin]

    @extend_schema(summary="Anular una Factura", responses={200: {"description": "Factura anulada y stock restaurado."}})
    def post(self, request, pk):
        try:
            anular_factura_y_restaurar_stock(factura_id=pk)
            return Response({"message": "Factura anulada y stock restaurado exitosamente."})
        except Factura.DoesNotExist:
            return Response({"error": "Factura no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        except FacturaAnulacionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)