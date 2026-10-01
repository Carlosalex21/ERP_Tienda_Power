from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.reportes.core.dashboard_service import obtener_metricas_dashboard
from apps.reportes.core.moneda_reporte import resolver_moneda_reporte
from apps.reportes.api.serializers import DashboardResponseSerializer


def _parsear_almacen_ids(valor: str | None) -> list[int] | None:
    """`?almacenes=3,7` -> `[3, 7]`; vacío/ausente -> `None` (sin filtrar, todas las sucursales)."""
    if not valor:
        return None
    ids = [p.strip() for p in valor.split(',') if p.strip().isdigit()]
    return [int(i) for i in ids] or None


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
            OpenApiParameter(name='moneda', description="Moneda de los montos: 'base' (defecto), 'referencia' o código ISO", type=OpenApiTypes.STR),
            OpenApiParameter(name='almacenes', description="IDs de sucursal/almacén separados por coma -- vacío = todas", type=OpenApiTypes.STR),
        ],
        responses={200: DashboardResponseSerializer}
    )
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        almacen_ids = _parsear_almacen_ids(request.query_params.get('almacenes'))

        moneda = resolver_moneda_reporte(request.query_params.get('moneda'))
        data = obtener_metricas_dashboard(start_date, end_date, request.user, moneda, almacen_ids)

        # Métricas propias del vertical contador (no vende bienes físicos,
        # las tarjetas de inventario/stock de arriba no le aplican) -- import
        # local a propósito: `apps.reportes` es compartido por TODAS las
        # verticales y no debe depender de que `apps.contabilidad` exista.
        if getattr(request.tenant, 'tipo_negocio', None) == 'contador':
            try:
                from apps.contabilidad.services import obtener_metricas_dashboard_contador
                data['contabilidad'] = obtener_metricas_dashboard_contador()
            except Exception:
                pass

        return Response(data)