from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsTenantAdmin
from apps.core.response import standard_response
from apps.clientes.models import Cliente
from apps.clientes.services.cliente_bulk_service import procesar_carga_masiva_clientes, ClienteBulkUploadError
from .serializers import ClienteSerializer, ClienteBulkUploadSerializer

class ClienteListCreateView(generics.ListCreateAPIView):
    """
    Vista para listar todos los clientes o crear un nuevo cliente.

    Sin paginación a propósito: el frontend (selector de clientes del POS,
    notas de crédito/débito) consume esto como un array plano. Sin este
    override heredaría la paginación global de DRF y devolvería
    ``{count, next, previous, results}``, rompiendo esos selectores en
    silencio (mismo bug ya detectado y corregido en ``RolViewSet``).
    """
    queryset = Cliente.objects.filter(activo=True)
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

class ClienteRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    Vista para ver, actualizar o eliminar (baja lógica) un cliente específico por su ID.
    """
    queryset = Cliente.objects.filter(activo=True)
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        # Un cliente puede tener facturas asociadas (`Factura.cliente`) --
        # borrarlo de verdad dejaría esas facturas sin datos del comprador,
        # justo el tipo de hueco que una auditoría fiscal no puede tener.
        instance.activo = False
        instance.save(update_fields=['activo'])


class ClienteBulkUploadView(APIView):
    """
    Endpoint para la carga masiva de Clientes (retail) desde un archivo CSV
    o Excel. Corre de forma síncrona -- ver el docstring de
    `procesar_carga_masiva_clientes`.

    Columnas reconocidas: `nombre` (obligatoria); `telefono`, `email`,
    `tipo_documento`, `documento` y `direccion` (opcionales).
    """
    permission_classes = [IsTenantAdmin]
    serializer_class = ClienteBulkUploadSerializer

    @extend_schema(
        summary="Carga Masiva de Clientes",
        request=ClienteBulkUploadSerializer,
        responses={
            200: {"description": "Archivo procesado. Ver el resumen de creados/actualizados/errores."},
            400: {"description": "Archivo inválido (formato no soportado o columnas obligatorias faltantes)."},
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']
        try:
            resultado = procesar_carga_masiva_clientes(
                file_content=uploaded_file.read(),
                file_name=uploaded_file.name,
            )
        except ClienteBulkUploadError as e:
            return Response({"error": str(e), "errores": e.errors}, status=status.HTTP_400_BAD_REQUEST)

        partes = [f"{resultado['clientes_creados']} creado(s)", f"{resultado['clientes_actualizados']} actualizado(s)"]
        if resultado['errores']:
            partes.append(f"{len(resultado['errores'])} fila(s) con error")
        resultado['message'] = f"Procesadas {resultado['total_filas']} fila(s): " + ", ".join(partes) + "."

        return standard_response(data=resultado, status_code=status.HTTP_200_OK)


PLANTILLA_CLIENTES_CSV = (
    "nombre,telefono,email,tipo_documento,documento,direccion\r\n"
    "Maria Perez,04121234567,maria@example.com,V,12345678,Av. Principal, Caracas\r\n"
)


class ClienteBulkUploadTemplateView(APIView):
    """Descarga una plantilla CSV con las columnas reconocidas por la carga masiva de clientes."""
    permission_classes = [IsTenantAdmin]

    @extend_schema(summary="Plantilla CSV de carga masiva de clientes", responses={200: {"description": "Archivo CSV."}})
    def get(self, request, *args, **kwargs):
        response = HttpResponse(PLANTILLA_CLIENTES_CSV, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="plantilla_clientes.csv"'
        return response