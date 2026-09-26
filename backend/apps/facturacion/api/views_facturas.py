from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from drf_spectacular.utils import extend_schema

from django.utils import timezone

from apps.core.permissions import IsAdminOrVendedor, IsAdminOrAlmacenista, IsTenantAdmin
from apps.core.response import error_response, standard_response

from ..models import Factura
from .serializers import FacturaSerializer
from ..services.factura_service import (
    FacturaAnulacionError,
    anular_factura_y_restaurar_stock,
)
from ..services.nota_entrega_service import (
    NotaEntregaError,
    confirmar_nota_entrega,
    convertir_nota_entrega_a_factura,
)


class FacturaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para la gestión completa de Facturas (Listar, Crear, Obtener, Actualizar, Eliminar).
    """
    queryset = Factura.objects.select_related('cliente', 'usuario', 'metodo_pago').prefetch_related('detalles__producto').order_by('-fecha_operacion')
    serializer_class = FacturaSerializer
    # Permite `?estado=pendiente` -- usado por el panel de Pedidos para no
    # traer/filtrar en el cliente todo el historial de facturas solo para
    # contar cuántas vienen del catálogo público sin confirmar. `?cliente=`
    # se usa para el historial de facturas de un cliente puntual (ej. las
    # facturas de honorarios de una EmpresaContable, ver `apps.contabilidad`).
    filterset_fields = ['estado', 'cliente', 'estado_preparacion', 'departamento_preparacion']

    def get_permissions(self):
        """
        Asigna permisos basados en la acción.

        - Lectura/escritura de facturas: Vendedores y Admins.
        - Eliminación: Solo Admins del tenant.
        """
        if self.action in ['list', 'retrieve', 'create', 'update', 'partial_update']:
            self.permission_classes = [IsAdminOrVendedor]
        elif self.action == 'destroy':
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()

    def perform_create(self, serializer):
        # El POS no mandaba `usuario` en el payload -- una venta quedaba sin
        # registro de quién la hizo. Por defecto se asume quien está logueado;
        # `vendedor` puede venir explícito si un admin está registrando una
        # venta que en realidad cerró otro empleado (ej. vendedor en la calle).
        extra = {}
        if serializer.validated_data.get('usuario') is None:
            extra['usuario'] = self.request.user
        if serializer.validated_data.get('vendedor') is None:
            extra['vendedor'] = serializer.validated_data.get('usuario') or self.request.user
        factura = serializer.save(**extra)
        # Una nota de entrega entrega la mercancía de inmediato -- su stock
        # sale al crearse, no cuando alguien la cobre después (ver
        # `apps.facturacion.services.nota_entrega_service`).
        if factura.estado == 'nota_entrega':
            confirmar_nota_entrega(factura)

    @action(detail=True, methods=['post'], url_path='convertir-a-factura')
    def convertir_a_factura(self, request, pk=None):
        """Convierte una nota de entrega en factura fiscal (le asigna correlativo) sin volver a tocar el stock."""
        factura = self.get_object()
        condicion_pago = request.data.get('condicion_pago', 'contado')
        try:
            factura = convertir_nota_entrega_a_factura(factura, condicion_pago=condicion_pago)
        except NotaEntregaError as e:
            return error_response([{"code": "nota_entrega_error", "detail": str(e), "field": None}], status_code=status.HTTP_400_BAD_REQUEST)
        return standard_response(data=self.get_serializer(factura).data)

    @action(detail=True, methods=['post'], url_path='marcar-preparado', permission_classes=[IsAdminOrAlmacenista])
    def marcar_preparado(self, request, pk=None):
        """
        El almacenista (o quien tenga acceso de bodega) marca que ya armó
        este pedido -- generaliza a retail/farmacia/B2B lo que en
        restaurantes hace `PedidoMesaViewSet.marcar_item_preparado` y en
        servicios el estado `listo` de una `OrdenServicio`: un paso de
        FULFILLMENT separado del cobro, no todo pedido pagado ya está armado.
        """
        factura = self.get_object()
        factura.estado_preparacion = 'listo'
        factura.preparado_por = request.user
        factura.fecha_preparado = timezone.now()
        factura.save(update_fields=['estado_preparacion', 'preparado_por', 'fecha_preparado'])
        return standard_response(data=self.get_serializer(factura).data)

    def perform_destroy(self, instance):
        # `correlativo` solo se asigna cuando la factura pasa a
        # pendiente/pagado (ver `Factura.save()`) -- si ya lo tiene, es un
        # documento fiscal real y borrarlo (aunque sea "solo" de la base de
        # datos) dejaría un hueco en la numeración que el SENIAT/DIAN/SUNAT
        # exigen que sea correlativa y sin saltos. La única vía para un
        # documento ya numerado es anularlo (`AnularFacturaView`), que deja
        # el registro y el motivo, no lo borra.
        if instance.correlativo:
            raise ValidationError({
                "detail": "Esta factura ya tiene un número fiscal asignado y no se puede eliminar. Anúlala en su lugar.",
            })
        # Una nota de entrega no tiene correlativo (nunca lo tuvo, ver
        # `Factura.save()`) pero SÍ puede haber descontado stock real -- si
        # se borrara así nomás, ese stock nunca volvería.
        if instance.inventario_afectado:
            raise ValidationError({
                "detail": "Esta nota de entrega ya descontó stock y no se puede eliminar. Anúlala en su lugar para restaurar el inventario.",
            })
        instance.delete()


class AnularFacturaView(APIView):
    """Anula una factura y restaura el stock, devolviendo la respuesta estándar."""

    permission_classes = [IsTenantAdmin]

    @extend_schema(
        summary="Anular una Factura",
        responses={
            200: {"description": "Factura anulada y stock restaurado."},
            404: {"description": "Factura no encontrada."},
            400: {"description": "Error de anulación."},
        },
    )
    def post(self, request, pk):
        """Procesa la anulación de la factura indicada."""
        try:
            anular_factura_y_restaurar_stock(factura_id=pk)
            return standard_response(
                data={"message": "Factura anulada y stock restaurado exitosamente."},
                status_code=status.HTTP_200_OK,
            )
        except Factura.DoesNotExist:
            return error_response(
                [{"code": "not_found", "detail": "Factura no encontrada.", "field": None}],
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except FacturaAnulacionError as e:
            return error_response(
                [{"code": "anulacion_error", "detail": str(e), "field": None}],
                status_code=status.HTTP_400_BAD_REQUEST,
            )
