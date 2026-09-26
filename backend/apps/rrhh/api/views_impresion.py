from io import BytesIO

from xhtml2pdf import pisa
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.rrhh.models import NominaEmpleado
from apps.configuracion.models import ConfiguracionEmpresa, Moneda
from apps.core.pdf_utils import obtener_logo_base64 as _obtener_logo_base64


class ReciboNominaImprimirView(APIView):
    """Genera el recibo de pago de UN empleado en UN período de nómina, en PDF (`rrhh/recibo_nomina_template.html`)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Imprimir/descargar Recibo de Pago en PDF",
        parameters=[
            OpenApiParameter(name='nomina_empleado_id', description='ID de la línea de nómina (empleado + período)', required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH),
            OpenApiParameter(name='download', description="Si es '1', fuerza la descarga en vez de abrir inline", required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: {'description': 'Recibo de pago en formato PDF.', 'content': {'application/pdf': {'schema': {'type': 'string', 'format': 'binary'}}}},
            404: {'description': 'Línea de nómina no encontrada.'},
        },
    )
    def get(self, request, nomina_empleado_id):
        try:
            linea = NominaEmpleado.objects.select_related('periodo', 'usuario', 'usuario__metadata').prefetch_related('conceptos').get(id=nomina_empleado_id)
        except NominaEmpleado.DoesNotExist:
            return HttpResponse("Línea de nómina no encontrada", status=404)

        # Un empleado normal solo puede ver/imprimir SU PROPIO recibo -- un
        # administrador (con acceso a la vista de nómina, ver `IsTenantAdmin`
        # en `PeriodoNominaViewSet`) puede imprimir el de cualquiera.
        es_admin = getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)
        if not es_admin and linea.usuario_id != request.user.id:
            return HttpResponse("Línea de nómina no encontrada", status=404)

        empresa_config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
        logo_base64 = _obtener_logo_base64(empresa_config.logo)
        moneda_base = Moneda.objects.filter(es_predeterminada=True).first()
        moneda_simbolo = (moneda_base.simbolo or moneda_base.codigo) if moneda_base else '$'

        conceptos = list(linea.conceptos.all())
        context = {
            'linea': linea,
            'periodo': linea.periodo,
            'empleado_nombre': linea.usuario.get_full_name() or linea.usuario.username,
            'numero_empleado': getattr(getattr(linea.usuario, 'metadata', None), 'numero_empleado', None),
            'empresa': empresa_config,
            'logo_base64': logo_base64,
            'moneda_simbolo': moneda_simbolo,
            'bonos': [c for c in conceptos if c.tipo == 'bono'],
            'deducciones': [c for c in conceptos if c.tipo == 'deduccion'],
        }

        html = render_to_string('rrhh/recibo_nomina_template.html', context)
        result = BytesIO()
        pisa.CreatePDF(html, dest=result)

        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        disposicion = 'attachment' if request.GET.get('download') == '1' else 'inline'
        nombre_archivo = f"recibo_nomina_{linea.usuario.username}_{linea.periodo.fecha_desde}.pdf"
        response['Content-Disposition'] = f'{disposicion}; filename="{nombre_archivo}"'
        return response
