import csv
from django.http import HttpResponse, JsonResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from http import HTTPStatus

from apps.reportes.models import Reportecliente
from apps.reportes.api.serializers import ReporteclienteSerializer
from apps.common.utils import generar_pdf, generar_excel

class ReporteclienteView(APIView):
    """Exporta el reporte de clientes a JSON, PDF, Excel o CSV."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        export_format = request.query_params.get('export', None)
        queryset = Reportecliente.objects.all().order_by("cliente__nombre")
        headers = ["Cliente", "Total Compras", "Cantidad Pedidos", "Producto Mas Comprado"]
        
        if export_format == 'pdf':
            return generar_pdf(queryset, headers, "Reporte de Clientes")
            
        if export_format == 'excel':
            return generar_excel(queryset, headers, "Reporte de Clientes")

        if export_format == 'csv':
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="reporte_clientes.csv"'
            writer = csv.writer(response)
            writer.writerow(headers)
            for reporte in queryset:
                writer.writerow([
                    reporte.cliente,
                    reporte.total_compras,
                    reporte.cantidad_pedidos,
                    reporte.producto_mas_comprado,
                ])
            return response
            
        # Por defecto, devuelve JSON
        serializer = ReporteclienteSerializer(queryset, many=True)
        return JsonResponse({"reportes": serializer.data}, status=HTTPStatus.OK)