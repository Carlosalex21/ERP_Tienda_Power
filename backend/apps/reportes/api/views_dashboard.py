from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.reportes.core.dashboard_service import obtener_metricas_dashboard
from apps.reportes.api.serializers import DashboardResponseSerializer

class DashboardDataView(APIView):
    """
    Proporciona datos agregados para el dashboard principal del tenant.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Obtener Datos del Dashboard",
        parameters=[
            OpenApiParameter(name='start_date', description='Fecha de inicio (YYYY-MM-DD)', type=OpenApiTypes.DATE),
            OpenApiParameter(name='end_date', description='Fecha de fin (YYYY-MM-DD)', type=OpenApiTypes.DATE),
        ],
        responses={200: DashboardResponseSerializer}
    )
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        data = obtener_metricas_dashboard(start_date, end_date, request.user) # Asegúrate que obtener_metricas_dashboard use select_related/prefetch_related internamente
        return Response(data)