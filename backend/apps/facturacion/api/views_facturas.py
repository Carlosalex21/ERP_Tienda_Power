from rest_framework import viewsets, status
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsAdminOrVendedor, IsTenantAdmin
from apps.core.response import error_response, standard_response

from ..models import Factura
from .serializers import FacturaSerializer
from ..services.factura_service import (
    FacturaAnulacionError,
    anular_factura_y_restaurar_stock,
)


class FacturaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para la gestión completa de Facturas (Listar, Crear, Obtener, Actualizar, Eliminar).
    """
    queryset = Factura.objects.select_related('cliente', 'usuario', 'metodo_pago').prefetch_related('detalles__producto')
    serializer_class = FacturaSerializer

    def get_permissions(self):
        """
        Asigna permisos basados en la acción.

        - Lectura/escritura de facturas: Vendedores y Admins.
        - Eliminación: Solo Admins del tenant.
        """
        if self.action in ['list', 'retrieve', 'create', 'update', 'partial_update']:
            self.permission_classes = [IsAdminOrVendedor]
        elif self.action == 'destroy':
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()


class AnularFacturaView(APIView):
    """Anula una factura y restaura el stock, devolviendo la respuesta estándar."""

    permission_classes = [IsTenantAdmin]

    @extend_schema(
        summary="Anular una Factura",
        responses={
            200: {"description": "Factura anulada y stock restaurado."},
            404: {"description": "Factura no encontrada."},
            400: {"description": "Error de anulación."},
        },
    )
    def post(self, request, pk):
        """Procesa la anulación de la factura indicada."""
        try:
            anular_factura_y_restaurar_stock(factura_id=pk)
            return standard_response(
                data={"message": "Factura anulada y stock restaurado exitosamente."},
                status_code=status.HTTP_200_OK,
            )
        except Factura.DoesNotExist:
            return error_response(
                [{"code": "not_found", "detail": "Factura no encontrada.", "field": None}],
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except FacturaAnulacionError as e:
            return error_response(
                [{"code": "anulacion_error", "detail": str(e), "field": None}],
                status_code=status.HTTP_400_BAD_REQUEST,
            )
