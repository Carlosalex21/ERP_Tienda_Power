from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

# Importamos nuestro servicio core
from apps.reportes.core.ventas_report_service import obtener_cierre_caja_service, obtener_reporte_ventas_service

# Importamos los serializers de tu código original
from erp.serializers import FacturaReportSerializer, VentaReporteSerializer, FacturaReporteSerializer

class CashClosingReportView(APIView):
    """Genera el reporte de cierre de caja para el día actual o uno específico."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_str = request.query_params.get('date', None)
        
        try:
            # Delegamos al Core
            target_date, total_caja, facturas = obtener_cierre_caja_service(date_str)
            
            serializer = FacturaReportSerializer(facturas, many=True)
            
            return Response({
                "report_date": target_date,
                "total_caja": total_caja,
                "transactions": serializer.data,
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReporteventaView(APIView):
    """Reporte general de ventas (sin detalles de productos)."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Delegamos al Core
            queryset = obtener_reporte_ventas_service(
                start_date_str=request.query_params.get("start_date"),
                end_date_str=request.query_params.get("end_date"),
                estado=request.query_params.get('estado')
            )
            
            serializer = VentaReporteSerializer(queryset, many=True)
            return Response({"reporte_detallado": serializer.data}, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "Error interno del servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FacturaDetalleReporteView(APIView):
    """Reporte detallado de ventas (incluyendo los ítems comprados en cada factura)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Delegamos al Core
            queryset = obtener_reporte_ventas_service(
                start_date_str=request.query_params.get("start_date"),
                end_date_str=request.query_params.get("end_date"),
                estado=request.query_params.get('estado'),
                cliente_id=request.query_params.get('cliente_id')
            )
            
            serializer = FacturaReporteSerializer(queryset, many=True)
            return Response({"reporte_detallado": serializer.data}, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)