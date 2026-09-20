from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrVendedor
from apps.core.throttling import ResilientScopedRateThrottle as ScopedRateThrottle

from ..models import OrdenServicio
from ..services import cerrar_orden_servicio, CerrarOrdenServicioError
from .serializers import OrdenServicioSerializer, CerrarOrdenServicioSerializer, OrdenServicioPublicoSerializer


class OrdenServicioViewSet(viewsets.ModelViewSet):
    queryset = OrdenServicio.objects.select_related('cliente', 'tecnico').filter(activo=True)
    serializer_class = OrdenServicioSerializer
    permission_classes = [IsAdminOrVendedor]

    def get_queryset(self):
        qs = super().get_queryset()
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save(update_fields=['activo'])

    @action(detail=True, methods=['post'])
    def cerrar(self, request, pk=None):
        orden = self.get_object()
        serializer = CerrarOrdenServicioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            factura = cerrar_orden_servicio(
                orden=orden,
                lineas=serializer.validated_data['lineas'],
                metodo_pago_id=serializer.validated_data['metodo_pago_id'],
                usuario=request.user,
                condicion_pago=serializer.validated_data['condicion_pago'],
                moneda_id=serializer.validated_data.get('moneda_id'),
            )
        except CerrarOrdenServicioError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"mensaje": "Orden facturada.", "factura_id": factura.id, "correlativo": factura.correlativo})


class OrdenServicioPublicoView(APIView):
    """
    Lo que abre el cliente al escanear el QR/abrir el link de seguimiento de
    su orden -- sin login, solo con el token opaco (ver
    `OrdenServicio.token_publico`).
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    def get(self, request, token):
        orden = OrdenServicio.objects.filter(token_publico=token, activo=True).first()
        if orden is None:
            return Response({"error": "Orden no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrdenServicioPublicoSerializer(orden).data)
