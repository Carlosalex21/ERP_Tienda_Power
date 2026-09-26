# apps/facturacion/api/views_reportes.py
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrVendedor

from ..services.pagos_service import reporte_cuentas_por_cobrar


class ReporteCuentasPorCobrarView(APIView):
    permission_classes = [IsAdminOrVendedor]

    def get(self, request):
        return Response(reporte_cuentas_por_cobrar())
