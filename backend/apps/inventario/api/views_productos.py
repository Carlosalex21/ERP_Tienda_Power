from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets
from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsTenantAdmin
from apps.core.response import standard_response
from ..models import Producto, Variacionproducto, PresentacionProducto
from .serializers import ProductoSerializer, VariacionproductoSerializer, PresentacionProductoSerializer
from .serializers_productos import ProductoBulkUploadSerializer
from ..services.product_service import procesar_carga_masiva_productos, ProductBulkUploadError

class ProductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para la gestión completa de Productos.
    Permite crear, leer, actualizar y eliminar (baja lógica) productos.
    """
    # La relación inversa real de Variacionproducto es 'variacionproducto_set'
    # (FK producto). Usamos ese nombre para el prefetch y evitar el error 500.
    #
    # select_related('configuracion_iva') evita un N+1: VariacionproductoSerializer
    # .get_base_imponible() accede a variacion.producto.configuracion_iva, y como
    # el prefetch de variaciones reutiliza la instancia de producto del queryset
    # principal, precargar aquí el FK cubre esa relación para TODAS sus variaciones
    # sin queries adicionales por producto.
    queryset = Producto.objects.select_related('configuracion_iva', 'moneda').prefetch_related(
        'variacionproducto_set', 'presentaciones',
    ).filter(activo=True)
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        # Eliminar (aunque sea baja lógica) queda reservado a admins, igual
        # que el resto de acciones destructivas del sistema fiscal.
        if self.action == 'destroy':
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()

    def perform_create(self, serializer):
        from apps.core.plan_limits import verificar_limite

        verificar_limite(
            self.request, 'limite_productos',
            Producto.objects.filter(activo=True).count(), 'productos',
        )
        serializer.save()

    def perform_destroy(self, instance):
        # Nunca un borrado físico: un producto que ya fue facturado no se
        # puede perder de la base de datos (rompería la línea de la factura
        # que lo vendió y la trazabilidad de esa venta ante una auditoría
        # fiscal). Se aplica siempre, haya sido facturado o no, para no
        # depender de detectarlo caso por caso -- más simple y sin huecos.
        instance.activo = False
        instance.save(update_fields=['activo'])

class VariacionproductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para la gestión de las Variaciones de un Producto.
    Permite crear, leer, actualizar y eliminar (baja lógica) variaciones.
    """
    queryset = Variacionproducto.objects.select_related('producto').filter(activo=True)
    serializer_class = VariacionproductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == 'destroy':
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()

    def perform_destroy(self, instance):
        # Misma razón que ProductoViewSet.perform_destroy.
        instance.activo = False
        instance.save(update_fields=['activo'])

class PresentacionProductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para las presentaciones de venta de un Producto (Unidad, Caja,
    Bulto...). Ver el docstring de `PresentacionProducto` para el diseño.
    """
    queryset = PresentacionProducto.objects.select_related('producto').filter(activo=True)
    serializer_class = PresentacionProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == 'destroy':
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()

    def perform_destroy(self, instance):
        # Baja lógica -- misma razón que ProductoViewSet.perform_destroy: una
        # presentación ya usada en una venta pasada no debe desaparecer de
        # golpe (Detallefactura no la referencia directamente hoy, pero
        # desactivar en vez de borrar es el patrón consistente del resto del
        # catálogo).
        instance.activo = False
        instance.save(update_fields=['activo'])


class ProductoBulkUploadView(APIView):
    """
    Endpoint para la carga masiva de Productos desde un archivo CSV o Excel.

    Corre de forma síncrona (ver docstring de `procesar_carga_masiva_productos`)
    y devuelve el resultado completo en la misma respuesta -- no depende de
    un worker de Celery, y el admin ve de inmediato cuántas filas se
    crearon/actualizaron y cuáles fallaron (con el motivo de cada una).

    Columnas reconocidas: `nombre` y `precio` (obligatorias); `codigo_barras`,
    `sku`, `stock_inicial`, `descripcion`, `categoria` e `iva` (opcionales).
    """
    permission_classes = [IsTenantAdmin]
    serializer_class = ProductoBulkUploadSerializer

    @extend_schema(
        summary="Carga Masiva de Productos",
        request=ProductoBulkUploadSerializer,
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
            resultado = procesar_carga_masiva_productos(
                file_content=uploaded_file.read(),
                file_name=uploaded_file.name,
            )
        except ProductBulkUploadError as e:
            return Response({"error": str(e), "errores": e.errors}, status=status.HTTP_400_BAD_REQUEST)

        partes = [f"{resultado['productos_creados']} creado(s)", f"{resultado['productos_actualizados']} actualizado(s)"]
        if resultado['errores']:
            partes.append(f"{len(resultado['errores'])} fila(s) con error")
        resultado['message'] = f"Procesadas {resultado['total_filas']} fila(s): " + ", ".join(partes) + "."

        return standard_response(data=resultado, status_code=status.HTTP_200_OK)


PLANTILLA_PRODUCTOS_CSV = (
    "nombre,precio,codigo_barras,sku,stock_inicial,categoria,iva,descripcion\r\n"
    "Botella de agua 500ml,67.00,7591234567890,AGUA-500,100,Bebidas,IVA General,Agua mineral sin gas\r\n"
)


class ProductoBulkUploadTemplateView(APIView):
    """Descarga una plantilla CSV con las columnas reconocidas por la carga masiva de productos."""
    permission_classes = [IsTenantAdmin]

    @extend_schema(summary="Plantilla CSV de carga masiva de productos", responses={200: {"description": "Archivo CSV."}})
    def get(self, request, *args, **kwargs):
        response = HttpResponse(PLANTILLA_PRODUCTOS_CSV, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="plantilla_productos.csv"'
        return response
