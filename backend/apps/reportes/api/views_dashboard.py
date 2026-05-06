from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.reportes.core.dashboard_service import obtener_metricas_dashboard

class DashboardDataView(APIView):
    """Panel principal de métricas de negocio."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Llamada al servicio CORE
        data = obtener_metricas_dashboard(start_date, end_date, request.user)
        
        return Response(data)