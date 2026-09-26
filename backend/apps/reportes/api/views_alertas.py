from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reportes.core.alertas_service import obtener_alertas


class AlertasView(APIView):
    """
    Centro de Alertas: cuentas por cobrar/pagar vencidas o por vencer, y
    productos con bajo stock -- una sola lista ordenada por urgencia, misma
    visibilidad que el dashboard (cualquier usuario autenticado del tenant).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(obtener_alertas())
