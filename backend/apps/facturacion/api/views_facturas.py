from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.facturacion.models import Factura
from apps.facturacion.api.serializers import FacturaSerializer
from apps.inventario.services.stock_service import restaurar_stock_item

class FacturaViewSet(viewsets.ReadOnlyModelViewSet):
    """Listado y detalle de facturas. Solo lectura por seguridad fiscal."""
    queryset = Factura.objects.all().order_by("-fecha_operacion")
    serializer_class = FacturaSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        """Lógica de anulación con restauración de inventario."""
        factura = self.get_object()
        if factura.estado == 'cancelada':
            return Response({"error": "Ya está anulada"}, status=status.HTTP_400_BAD_REQUEST)

        # Restaurar Stock usando el servicio de inventario
        for detalle in factura.detalles.all():
            item = detalle.variante if detalle.variante else detalle.producto
            restaurar_stock_item(item, detalle.cantidad)

        factura.estado = 'cancelada'
        factura.save()
        return Response({"mensaje": "Factura anulada y stock devuelto."})