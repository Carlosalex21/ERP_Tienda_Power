from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reportes.core.alertas_service import obtener_alertas
from apps.reportes.api.views_dashboard import _parsear_almacen_ids


class AlertasView(APIView):
    """
    Centro de Alertas: cuentas por cobrar/pagar vencidas o por vencer, y
    productos con bajo stock -- una sola lista ordenada por urgencia, misma
    visibilidad que el dashboard (cualquier usuario autenticado del tenant).

    `?almacenes=3,7` filtra las alertas de bajo stock a esas sucursales/
    almacenes (las demás fuentes no tienen sucursal asociada, ver
    `apps.reportes.core.alertas_service.obtener_alertas`).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        almacen_ids = _parsear_almacen_ids(request.query_params.get('almacenes'))
        return Response(obtener_alertas(almacen_ids))
