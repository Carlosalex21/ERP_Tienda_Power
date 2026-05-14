from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from apps.facturacion.models import Factura

# Importamos nuestro servicio core
from apps.reportes.core.ventas_report_service import obtener_cierre_caja_service, obtener_reporte_ventas_service

# Importamos los serializers de tu código original
from apps.reportes.api.serializers import FacturaReportSerializer, VentaReporteSerializer, FacturaReporteSerializer

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
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Reporte de Ventas",
        parameters=[
            OpenApiParameter(name='fecha_inicio', description='Fecha de inicio (YYYY-MM-DD)', type=OpenApiTypes.DATE),
            OpenApiParameter(name='fecha_fin', description='Fecha de fin (YYYY-MM-DD)', type=OpenApiTypes.DATE),
        ]
    )
    def get(self, request):
        queryset = Factura.objects.select_related('cliente', 'usuario').order_by('-fecha_operacion')
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin = request.query_params.get('fecha_fin')
        if fecha_inicio and fecha_fin:
            queryset = queryset.filter(fecha_operacion__range=[fecha_inicio, fecha_fin])
        
        serializer = VentaReporteSerializer(queryset, many=True)
        return Response(serializer.data)

class FacturaDetalleReporteView(APIView):
    permission_classes = [IsAuthenticated]


class FacturaDetalleReporteView(APIView):
    """Reporte detallado de ventas (incluyendo los ítems comprados en cada factura)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Delegamos al Core
            queryset = obtener_reporte_ventas_service(
                start_date_str=request.query_params.get("fecha_inicio"), # Usar los mismos nombres que en ReporteventaView
                end_date_str=request.query_params.get("end_date"),
                estado=request.query_params.get('estado'),
                cliente_id=request.query_params.get('cliente_id')
            )
            
            serializer = FacturaReporteSerializer(queryset, many=True)
            return Response({"reporte_detallado": serializer.data}, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)