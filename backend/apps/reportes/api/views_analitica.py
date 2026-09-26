from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.reportes.core.analitica_service import obtener_analitica_completa
from apps.reportes.core.moneda_reporte import resolver_moneda_reporte


class AnaliticaView(APIView):
    """Tendencias mensuales, comparativa mes-contra-mes y proyección simple."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Obtener Analítica de Ventas (tendencias, comparativas, proyección)",
        parameters=[
            OpenApiParameter(name='meses', description='Cuántos meses hacia atrás incluir en la tendencia (default 12)', type=OpenApiTypes.INT),
            OpenApiParameter(name='moneda', description="Moneda de los montos: 'base' (defecto), 'referencia' o código ISO", type=OpenApiTypes.STR),
        ],
    )
    def get(self, request):
        try:
            meses = int(request.query_params.get('meses', 12))
        except (TypeError, ValueError):
            meses = 12
        meses = max(3, min(meses, 24))
        moneda = resolver_moneda_reporte(request.query_params.get('moneda'))
        return Response(obtener_analitica_completa(meses, moneda))
