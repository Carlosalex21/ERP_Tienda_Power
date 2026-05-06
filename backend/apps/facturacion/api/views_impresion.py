import os, base64
from io import BytesIO
from xhtml2pdf import pisa
from django.conf import settings
from django.template.loader import render_to_string
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from apps.facturacion.models import Factura

class FacturaImprimirView(APIView):
    """Genera el ticket fiscal/comprobante en formato PDF."""
    permission_classes = [IsAuthenticated]

    def get(self, request, factura_id):
        try:
            factura = Factura.objects.select_related('cliente', 'usuario', 'metodo_pago').get(id=factura_id)
            
            # Preparación de Logo para el PDF
            logo_base64 = self._obtener_logo_base64()

            context = {
                'factura': factura,
                'detalles': factura.detalles.all(),
                'empresa': settings.DATOS_EMPRESA, 
                'logo_base64': logo_base64,
                'paper_size': request.GET.get('paper_size', '58')
            }

            html = render_to_string('tickets/ticket_template.html', context)
            result = BytesIO()
            pisa.CreatePDF(html, dest=result)

            return HttpResponse(result.getvalue(), content_type='application/pdf')
        except Factura.DoesNotExist:
            return HttpResponse("Factura no encontrada", status=404)

    def _obtener_logo_base64(self):
        path = os.path.join(settings.BASE_DIR, 'img', 'LOGO-POWER.png')
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        return None