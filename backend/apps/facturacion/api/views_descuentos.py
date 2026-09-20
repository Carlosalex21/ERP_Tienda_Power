from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from decimal import Decimal, InvalidOperation

from apps.core.permissions import IsAdminOrVendedor
from apps.facturacion.models import Factura, Detallefactura, Cupondescuento
from apps.facturacion.api.serializers import FacturaSerializer, CupondescuentoSerializer
from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura

class ActualizarDescuentoDetalleView(APIView):
    """Aplica descuento a una línea de producto específica."""
    # Descuentos son una decisión de precio/venta -- antes era
    # `IsAuthenticated` a secas, así que cualquier empleado (ej. un
    # almacenista) podía descontarle lo que quisiera a cualquier factura.
    permission_classes = [IsAdminOrVendedor]

    def post(self, request):
        detalle_id = request.data.get("detalle_id")
        try:
            descuento = Decimal(request.data.get("descuento", 0))
        except (InvalidOperation, TypeError):
            return Response({"error": "Descuento inválido."}, status=status.HTTP_400_BAD_REQUEST)

        # `detalle.descuento` es un PORCENTAJE aplicado como
        # `total * (1 - descuento/100)` (ver `calculos_service.py`) --
        # sin este rango, un valor negativo funciona como un RECARGO (sube
        # el precio) y uno mayor a 100 deja la línea en total negativo.
        # Antes no se validaba nada: cualquier empleado podía mandar
        # cualquier número.
        if descuento < 0 or descuento > 100:
            return Response({"error": "El descuento debe estar entre 0 y 100."}, status=status.HTTP_400_BAD_REQUEST)

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
    permission_classes = [IsAdminOrVendedor]

    def post(self, request):
        factura_id = request.data.get("factura_id")
        try:
            descuento_global = Decimal(request.data.get("descuento_global", 0))
        except (InvalidOperation, TypeError):
            return Response({"error": "Descuento inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if descuento_global < 0:
            return Response({"error": "El descuento no puede ser negativo."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            factura = Factura.objects.get(id=factura_id)
        except Factura.DoesNotExist:
            return Response({"error": "Factura no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        # `descuento_global` es un MONTO FIJO restado directo del subtotal
        # (`base_imponible = total_subtotal - descuento_global`, ver
        # `calculos_service.py`) -- sin este tope, un descuento mayor al
        # subtotal dejaba la base imponible (y el total) en negativo.
        if descuento_global > factura.subtotal:
            return Response(
                {"error": "El descuento no puede ser mayor al subtotal de la factura."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        factura.detalles.all().update(descuento=descuento_global)
        factura.descuento_global = descuento_global
        factura.save()

        recalcular_y_guardar_factura(factura)
        return Response(FacturaSerializer(factura).data)

class CupondescuentoViewSet(viewsets.ModelViewSet):
    queryset = Cupondescuento.objects.all()
    serializer_class = CupondescuentoSerializer
    permission_classes = [IsAdminOrVendedor]