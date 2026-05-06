from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, viewsets
from decimal import Decimal

from apps.facturacion.models import Factura, Detallefactura, Cupondescuento
from apps.facturacion.api.serializers import FacturaSerializer, CupondescuentoSerializer
from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura

class ActualizarDescuentoDetalleView(APIView):
    """Aplica descuento a una línea de producto específica."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        detalle_id = request.data.get("detalle_id")
        descuento = Decimal(request.data.get("descuento", 0))

        try:
            detalle = Detallefactura.objects.get(id=detalle_id)
            detalle.descuento = descuento
            detalle.save()
            
            recalcular_y_guardar_factura(detalle.factura)
            return Response(FacturaSerializer(detalle.factura).data)
        except Detallefactura.DoesNotExist:
            return Response({"error": "Item no encontrado"}, status=status.HTTP_404_NOT_FOUND)

class ActualizarDescuentoGlobalView(APIView):
    """Aplica el mismo descuento a todos los productos de la factura."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        factura_id = request.data.get("factura_id")
        descuento_global = Decimal(request.data.get("descuento_global", 0))

        try:
            factura = Factura.objects.get(id=factura_id)
            factura.detalles.all().update(descuento=descuento_global)
            factura.descuento_global = descuento_global
            factura.save()
            
            recalcular_y_guardar_factura(factura)
            return Response(FacturaSerializer(factura).data)
        except Factura.DoesNotExist:
            return Response({"error": "Factura no encontrada"}, status=status.HTTP_404_NOT_FOUND)

class CupondescuentoViewSet(viewsets.ModelViewSet):
    queryset = Cupondescuento.objects.all()
    serializer_class = CupondescuentoSerializer
    permission_classes = [IsAuthenticated]