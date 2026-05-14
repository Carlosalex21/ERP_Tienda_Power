import os, base64
from io import BytesIO
from xhtml2pdf import pisa
from django.conf import settings
from django.template.loader import render_to_string
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from apps.facturacion.models import Factura
from apps.configuracion.models import ConfiguracionEmpresa

class FacturaImprimirView(APIView):
    """Genera el ticket fiscal/comprobante en formato PDF."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Imprimir Factura en PDF",
        description="Genera y devuelve un archivo PDF para la factura especificada. El formato de papel se puede especificar como un parámetro de consulta.",
        parameters=[
            OpenApiParameter(name='factura_id', description='ID de la factura a imprimir', required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH),
            OpenApiParameter(name='paper_size', description="Tamaño del papel ('58' o '80')", required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: {
                'description': 'Factura en formato PDF.',
                'content': {'application/pdf': {'schema': {'type': 'string', 'format': 'binary'}}}
            },
            404: {'description': 'Factura no encontrada.'}
        }
    )
    def get(self, request, factura_id):
        try:
            factura = Factura.objects.select_related('cliente', 'usuario', 'metodo_pago').get(id=factura_id)
            # Obtenemos la configuración de la empresa del tenant actual
            empresa_config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
            
            # Preparación de Logo para el PDF
            logo_base64 = self._obtener_logo_base64(empresa_config.logo)

            context = {
                'factura': factura,
                'detalles': factura.detalles.all(),
                'empresa': empresa_config, 
                'logo_base64': logo_base64,
                'paper_size': request.GET.get('paper_size', '58')
            }

            html = render_to_string('tickets/ticket_template.html', context)
            result = BytesIO()
            pisa.CreatePDF(html, dest=result)

            return HttpResponse(result.getvalue(), content_type='application/pdf')
        except Factura.DoesNotExist:
            return HttpResponse("Factura no encontrada", status=404)

    def _obtener_logo_base64(self, logo_field):
        if logo_field and hasattr(logo_field, 'path') and os.path.exists(logo_field.path):
            with open(logo_field.path, "rb") as f:
                return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        return None