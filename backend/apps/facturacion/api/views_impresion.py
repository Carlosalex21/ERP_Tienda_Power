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
from apps.facturacion.models import Factura, NotaCredito, NotaDebito
from apps.configuracion.models import ConfiguracionEmpresa, Moneda


def _factura_pertenece_al_usuario(user, factura) -> bool:
    """
    True si `user` puede ver el PDF de `factura`.

    Los empleados (sin `cliente_b2b` asociado -- vendedores, cajeros,
    administradores) pueden imprimir cualquier factura del tenant, como ya
    hacían: es una operación normal de POS/mostrador reimprimir el
    comprobante de cualquier venta. Un cliente del PORTAL B2B, en cambio,
    solo puede ver SUS PROPIAS facturas -- antes de esta función, cualquier
    usuario autenticado (incluido un cliente B2B externo) podía descargar
    la factura de CUALQUIER OTRO cliente con solo cambiar el `factura_id`
    en la URL.
    """
    cliente_b2b = getattr(user, 'cliente_b2b', None)
    if cliente_b2b is None:
        return True
    return factura is not None and factura.cliente_b2b_id == cliente_b2b.id


def _obtener_logo_base64(logo_field):
    if logo_field and hasattr(logo_field, 'path') and os.path.exists(logo_field.path):
        with open(logo_field.path, "rb") as f:
            return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
    return None


def _generar_pdf_nota(nota, tipo_documento_label: str, download: bool) -> HttpResponse:
    """
    Genera el PDF de una Nota de Crédito/Débito (`nota_template.html`).

    La nota no tiene su propia moneda (usa la de la factura asociada, ver
    `factura_moneda_codigo` en el serializer) -- por eso la moneda y la tasa
    para el "equivalente en moneda base" salen de `nota.factura`, igual que
    ya hace el resto del sistema (Pedidos, Libro de Ventas) para no
    etiquetar un monto con la moneda equivocada.
    """
    empresa_config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
    logo_base64 = _obtener_logo_base64(empresa_config.logo)

    factura = nota.factura
    moneda_base = Moneda.objects.filter(es_predeterminada=True).first()
    moneda_simbolo = (factura.moneda.simbolo or factura.moneda.codigo) if factura and factura.moneda else (
        (moneda_base.simbolo or moneda_base.codigo) if moneda_base else ''
    )
    mostrar_total_base = bool(factura and factura.moneda and moneda_base and factura.moneda_id != moneda_base.id)

    context = {
        'nota': nota,
        'tipo_documento_label': tipo_documento_label,
        'empresa': empresa_config,
        'logo_base64': logo_base64,
        'moneda_simbolo': moneda_simbolo,
        'moneda_base_simbolo': (moneda_base.simbolo or moneda_base.codigo) if moneda_base else '',
        'mostrar_total_base': mostrar_total_base,
    }

    html = render_to_string('tickets/nota_template.html', context)
    result = BytesIO()
    pisa.CreatePDF(html, dest=result)

    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    disposicion = 'attachment' if download else 'inline'
    response['Content-Disposition'] = f'{disposicion}; filename="{tipo_documento_label.lower().replace(" ", "_")}_{nota.numero_nota}.pdf"'
    return response


class FacturaImprimirView(APIView):
    """
    Genera la factura/ticket en PDF (`xhtml2pdf`, ver
    `templates/tickets/ticket_template.html`). Sirve tanto para el ticket
    térmico del POS (`paper_size=58` o `80`) como para una hoja completa
    (sin `paper_size`, tamaño A4) -- el mismo template ajusta el CSS según
    el parámetro.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Imprimir/descargar Factura en PDF",
        description="Genera y devuelve un archivo PDF para la factura especificada. El formato de papel se puede especificar como un parámetro de consulta.",
        parameters=[
            OpenApiParameter(name='factura_id', description='ID de la factura a imprimir', required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH),
            OpenApiParameter(name='paper_size', description="Tamaño del papel ('58', '80' o vacío para hoja completa)", required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
            OpenApiParameter(name='download', description="Si es '1', fuerza la descarga en vez de abrir inline", required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
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
            factura = Factura.objects.select_related(
                'cliente', 'usuario', 'vendedor', 'metodo_pago', 'moneda',
            ).prefetch_related(
                'detalles__producto', 'detalles__variante',
            ).get(id=factura_id)
        except Factura.DoesNotExist:
            return HttpResponse("Factura no encontrada", status=404)

        if not _factura_pertenece_al_usuario(request.user, factura):
            return HttpResponse("Factura no encontrada", status=404)

        empresa_config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
        logo_base64 = _obtener_logo_base64(empresa_config.logo)

        moneda_base = Moneda.objects.filter(es_predeterminada=True).first()
        moneda_simbolo = (factura.moneda.simbolo or factura.moneda.codigo) if factura.moneda else (
            (moneda_base.simbolo or moneda_base.codigo) if moneda_base else ''
        )
        mostrar_total_base = bool(factura.moneda and moneda_base and factura.moneda_id != moneda_base.id)

        vendedor = factura.vendedor or factura.usuario
        vendedor_nombre = (vendedor.get_full_name() or vendedor.username) if vendedor else None

        context = {
            'factura': factura,
            'detalles': factura.detalles.all(),
            'empresa': empresa_config,
            'logo_base64': logo_base64,
            'paper_size': request.GET.get('paper_size', ''),
            'moneda_simbolo': moneda_simbolo,
            'moneda_base_simbolo': (moneda_base.simbolo or moneda_base.codigo) if moneda_base else '',
            'mostrar_total_base': mostrar_total_base,
            'vendedor_nombre': vendedor_nombre,
        }

        html = render_to_string('tickets/ticket_template.html', context)
        result = BytesIO()
        pisa.CreatePDF(html, dest=result)

        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        disposicion = 'attachment' if request.GET.get('download') == '1' else 'inline'
        nombre_archivo = f"factura_{factura.correlativo or factura.id}.pdf"
        response['Content-Disposition'] = f'{disposicion}; filename="{nombre_archivo}"'
        return response


class NotaCreditoImprimirView(APIView):
    """Genera la Nota de Crédito en PDF (`tickets/nota_template.html`)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Imprimir/descargar Nota de Crédito en PDF",
        parameters=[
            OpenApiParameter(name='nota_id', description='ID de la nota a imprimir', required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH),
            OpenApiParameter(name='download', description="Si es '1', fuerza la descarga en vez de abrir inline", required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: {'description': 'Nota de Crédito en formato PDF.', 'content': {'application/pdf': {'schema': {'type': 'string', 'format': 'binary'}}}},
            404: {'description': 'Nota no encontrada.'},
        }
    )
    def get(self, request, nota_id):
        try:
            nota = NotaCredito.objects.select_related('factura__cliente', 'factura__moneda').get(id=nota_id)
        except NotaCredito.DoesNotExist:
            return HttpResponse("Nota de crédito no encontrada", status=404)
        if not _factura_pertenece_al_usuario(request.user, nota.factura):
            return HttpResponse("Nota de crédito no encontrada", status=404)
        return _generar_pdf_nota(nota, "Nota de Crédito", request.GET.get('download') == '1')


class NotaDebitoImprimirView(APIView):
    """Genera la Nota de Débito en PDF (`tickets/nota_template.html`)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Imprimir/descargar Nota de Débito en PDF",
        parameters=[
            OpenApiParameter(name='nota_id', description='ID de la nota a imprimir', required=True, type=OpenApiTypes.INT, location=OpenApiParameter.PATH),
            OpenApiParameter(name='download', description="Si es '1', fuerza la descarga en vez de abrir inline", required=False, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: {'description': 'Nota de Débito en formato PDF.', 'content': {'application/pdf': {'schema': {'type': 'string', 'format': 'binary'}}}},
            404: {'description': 'Nota no encontrada.'},
        }
    )
    def get(self, request, nota_id):
        try:
            nota = NotaDebito.objects.select_related('factura__cliente', 'factura__moneda').get(id=nota_id)
        except NotaDebito.DoesNotExist:
            return HttpResponse("Nota de débito no encontrada", status=404)
        if not _factura_pertenece_al_usuario(request.user, nota.factura):
            return HttpResponse("Nota de débito no encontrada", status=404)
        return _generar_pdf_nota(nota, "Nota de Débito", request.GET.get('download') == '1')
