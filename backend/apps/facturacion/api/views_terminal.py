from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone

from apps.facturacion.models import Factura, Detallefactura
from apps.facturacion.api.serializers import FacturaSerializer
from apps.facturacion.services.ordenes_service import agg_producto_a_orden_service
from apps.facturacion.services.pagos_service import procesar_pago_factura_service, calcular_saldo_pendiente

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
    """
    Procesa el cierre de la factura y el registro de uno o varios pagos.

    Body esperado:
        ``factura_id``: int.
        ``pagos``: lista de ``{metodo_pago_id, monto, monto_recibido?, referencia?}``
            -- puede traer más de una entrada (pago dividido en varios
            métodos) y no tiene que cubrir el total (abono a crédito).
            Vacía cuando ``estado == "pendiente"``.
        ``estado``: ``"pendiente"`` para "pagar luego" (no registra pagos).
        ``datos_adicionales``: ``{nombre_cliente, comentario, metodo_pago_id}``
            -- solo aplica al caso "pendiente".

    Por compatibilidad, también acepta el body antiguo de un solo pago
    (``metodo_pago`` + ``monto_recibido``) y lo trata como una lista de un
    elemento.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        factura_id = request.data.get("factura_id")
        if not factura_id:
            return Response({"error": "El campo 'factura_id' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        pagos = request.data.get("pagos")
        if pagos is None:
            # Body antiguo: un solo método + monto recibido.
            metodo_pago_id = request.data.get("metodo_pago")
            monto_recibido = request.data.get("monto_recibido")
            if metodo_pago_id and monto_recibido is not None:
                pagos = [{
                    "metodo_pago_id": metodo_pago_id,
                    "monto": monto_recibido,
                    "monto_recibido": monto_recibido,
                }]
            else:
                pagos = []

        datos_adicionales = request.data.get("datos_adicionales", {}) or {}
        if not datos_adicionales.get("metodo_pago_id") and request.data.get("metodo_pago"):
            datos_adicionales["metodo_pago_id"] = request.data.get("metodo_pago")

        try:
            factura, transacciones = procesar_pago_factura_service(
                factura_id=factura_id,
                pagos=pagos,
                estado_override=(request.data.get("estado") or "").lower(),
                datos_adicionales=datos_adicionales,
                usuario=request.user,
            )
            return Response({
                "mensaje": "Pago procesado",
                "factura": FacturaSerializer(factura).data,
                "saldo_pendiente": str(calcular_saldo_pendiente(factura)),
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