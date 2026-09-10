from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets
from drf_spectacular.utils import extend_schema

from ..models import Producto, Variacionproducto
from .serializers import ProductoSerializer, VariacionproductoSerializer
from .serializers_productos import ProductoBulkUploadSerializer
from ..tasks import task_procesar_carga_masiva_productos

class ProductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para la gestión completa de Productos.
    Permite crear, leer, actualizar y eliminar productos.
    """
    # La relación inversa real de Variacionproducto es 'variacionproducto_set'
    # (FK producto). Usamos ese nombre para el prefetch y evitar el error 500.
    queryset = Producto.objects.prefetch_related('variacionproducto_set').filter(activo=True)
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

class VariacionproductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para la gestión de las Variaciones de un Producto.
    Permite crear, leer, actualizar y eliminar variaciones.
    """
    queryset = Variacionproducto.objects.select_related('producto').all()
    serializer_class = VariacionproductoSerializer
    permission_classes = [permissions.IsAuthenticated]

class ProductoBulkUploadView(APIView):
    """
    Endpoint para la carga masiva de Productos desde un archivo CSV o Excel.

    Columnas recomendadas en el archivo:
    - `nombre`, `codigo_barras`, `stock_inicial`, `precio_compra`, `precio_venta`
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProductoBulkUploadSerializer

    @extend_schema(
        summary="Carga Masiva de Productos",
        request=ProductoBulkUploadSerializer,
        responses={
            202: {"description": "Procesamiento iniciado."},
            400: {"description": "Archivo inválido o error en los datos."},
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']
        tenant = request.tenant
        user = request.user
        
        # Delegamos el procesamiento pesado a una tarea asíncrona de Celery
        task_procesar_carga_masiva_productos.delay(
            file_content=uploaded_file.read(),
            file_name=uploaded_file.name,
            tenant_id=tenant.id,
            user_id=user.id
        )
        
        return Response(
            {"message": "Archivo de productos recibido. El procesamiento ha comenzado en segundo plano."},
            status=status.HTTP_202_ACCEPTED
        )
