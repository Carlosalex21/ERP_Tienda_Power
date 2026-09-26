from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAdminOrVendedor

from ..models import Garantia, ReclamoPostventa
from ..services import crear_reclamo, cambiar_estado_reclamo, PostventaError
from .serializers import (
    GarantiaSerializer, ReclamoPostventaSerializer, CrearReclamoSerializer, CambiarEstadoReclamoSerializer,
)


class GarantiaViewSet(viewsets.ReadOnlyModelViewSet):
    """Garantías generadas automáticamente al pagarse una venta -- de solo lectura, nunca se crean/editan a mano."""
    queryset = Garantia.objects.select_related('producto', 'cliente', 'factura').prefetch_related('reclamos')
    serializer_class = GarantiaSerializer
    permission_classes = [IsAdminOrVendedor]

    def get_queryset(self):
        qs = super().get_queryset()
        estado = self.request.query_params.get('estado')
        if estado == 'vigente':
            from django.utils import timezone
            qs = qs.filter(fecha_vencimiento__gte=timezone.localdate())
        elif estado == 'vencida':
            from django.utils import timezone
            qs = qs.filter(fecha_vencimiento__lt=timezone.localdate())
        cliente_id = self.request.query_params.get('cliente')
        if cliente_id:
            qs = qs.filter(cliente_id=cliente_id)
        return qs


class ReclamoPostventaViewSet(viewsets.ModelViewSet):
    """Reclamos/tickets de postventa -- creación vía `crear_reclamo` (valida cliente-o-contacto libre); cambios de estado van por la acción dedicada para no reabrir uno ya cerrado."""
    queryset = ReclamoPostventa.objects.select_related('garantia', 'factura', 'producto', 'cliente', 'usuario_asignado')
    serializer_class = ReclamoPostventaSerializer
    permission_classes = [IsAdminOrVendedor]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = CrearReclamoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            reclamo = crear_reclamo(
                titulo=data['titulo'], descripcion=data.get('descripcion', ''),
                cliente_id=data.get('cliente'), nombre_contacto_libre=data.get('nombre_contacto_libre', ''),
                telefono_contacto=data.get('telefono_contacto', ''),
                factura_id=data.get('factura'), producto_id=data.get('producto'), garantia_id=data.get('garantia'),
                prioridad=data.get('prioridad', 'media'), usuario_creador=request.user,
            )
        except PostventaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(reclamo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cambiar-estado')
    def cambiar_estado(self, request, pk=None):
        reclamo = self.get_object()
        serializer = CambiarEstadoReclamoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cambiar_estado_reclamo(reclamo, serializer.validated_data['estado'], serializer.validated_data.get('resolucion', ''))
        except PostventaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(reclamo).data)
