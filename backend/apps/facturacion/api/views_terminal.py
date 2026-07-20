from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone

from apps.facturacion.models import Factura, Detallefactura
from apps.facturacion.api.serializers import FacturaSerializer
from apps.facturacion.services.ordenes_service import agg_producto_a_orden_service
from apps.facturacion.services.pagos_service import procesar_pago_factura_service

class BarcodeScanView(APIView):
    """Agrega o quita productos de la cuenta actual mediante escaneo."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cliente_id = request.data.get("cliente_id")
        barcode = request.data.get("codigo_barras")
        cantidad = int(request.data.get("cantidad", 1))
        eliminar = request.data.get("eliminar", False)

        if not cliente_id or not barcode:
            return Response({"error": "Faltan datos de cliente o código."}, status=status.HTTP_400_BAD_REQUEST)

        factura, error = agg_producto_a_orden_service(
            usuario=request.user, cliente_id=cliente_id, barcode=barcode, 
            cantidad=cantidad, eliminar=eliminar
        )
        
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "mensaje": "Operación exitosa",
            "factura": FacturaSerializer(factura).data
        })

class PagoView(APIView):
    """Procesa el cierre de la factura y el registro del pago."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        factura_id = request.data.get("factura_id")
        metodo_pago_id = request.data.get("metodo_pago") # Clave consistente con el ModelSerializer
        monto = request.data.get("monto_recibido")
        
        if not factura_id or not metodo_pago_id:
            return Response({"error": "Los campos 'factura_id' y 'metodo_pago' son requeridos."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            factura, transaccion = procesar_pago_factura_service(
                factura_id=factura_id,
                metodo_pago_id=metodo_pago_id,
                monto_recibido=monto,
                estado_override=request.data.get("estado", "").lower(),
                datos_adicionales=request.data.get("datos_adicionales", {})
            )
            return Response({
                "mensaje": "Pago procesado",
                "factura": FacturaSerializer(factura).data
            })
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class FacturaPendienteView(APIView):
    """Recupera la factura abierta de un cliente para continuar la venta."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cliente_id = request.query_params.get("cliente_id")
        factura = Factura.objects.filter(
            cliente_id=cliente_id, estado="abierta", 
            fecha_operacion__date=timezone.now().date()
        ).first()

        if not factura:
            return Response({"error": "No hay cuenta pendiente."}, status=status.HTTP_404_NOT_FOUND)
        
        return Response(FacturaSerializer(factura).data)

class ResetFacturaView(APIView):
    """Cancela la cuenta actual y vacía los items."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cliente_id = request.data.get("cliente_id")
        factura = Factura.objects.filter(cliente_id=cliente_id, estado="abierta").first()
        if factura:
            factura.detalles.all().delete()
            factura.estado = "cancelada"
            factura.save()
            return Response({"mensaje": "Cuenta reiniciada."})
        return Response({"error": "No se encontró cuenta activa."}, status=status.HTTP_404_NOT_FOUND)