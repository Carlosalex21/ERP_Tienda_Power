from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.reportes.core.analitica_service import obtener_analitica_completa


class AnaliticaView(APIView):
    """Tendencias mensuales, comparativa mes-contra-mes y proyección simple."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Obtener Analítica de Ventas (tendencias, comparativas, proyección)",
        parameters=[
            OpenApiParameter(name='meses', description='Cuántos meses hacia atrás incluir en la tendencia (default 12)', type=OpenApiTypes.INT),
        ],
    )
    def get(self, request):
        meses = int(request.query_params.get('meses', 12))
        meses = max(3, min(meses, 24))
        return Response(obtener_analitica_completa(meses))
