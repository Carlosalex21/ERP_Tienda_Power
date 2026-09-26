# apps/proveedores/api/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrVendedor, IsAdminOrAlmacenista
from apps.proveedores.models import Proveedor, CuentaPorPagar, OrdenCompra
from apps.proveedores.api.serializers import (
    ProveedorSerializer, CuentaPorPagarSerializer, RegistrarPagoProveedorSerializer,
    OrdenCompraSerializer, CrearOrdenCompraSerializer, RegistrarRecepcionSerializer,
)
from apps.proveedores.core.proveedores_service import (
    desactivar_proveedor_service, registrar_pago_proveedor, reporte_cuentas_por_pagar,
    CuentaPorPagarError,
)
from apps.proveedores.core.compras_service import (
    crear_orden_compra, enviar_orden_compra, cancelar_orden_compra, registrar_recepcion_orden_compra,
    OrdenCompraError,
)

class ProveedorViewSet(viewsets.ModelViewSet):
    """
    CRUD completo de proveedores delegando operaciones críticas al Core.
    """
    queryset = Proveedor.objects.filter(activo=True).order_by('id')
    serializer_class = ProveedorSerializer
    # Incluye datos fiscales SENIAT (identificador_fiscal,
    # es_contribuyente_especial) -- antes cualquier empleado autenticado
    # podía editarlos.
    permission_classes = [IsAdminOrVendedor]

    def destroy(self, request, *args, **kwargs):
        """
        Sobreescribimos el método DELETE de la API para usar nuestro servicio.
        """
        proveedor = self.get_object()
        try:
            # Delegamos la regla de negocio al CORE
            desactivar_proveedor_service(proveedor.id)
            return Response(
                {"estado": "eliminado", "mensaje": "Proveedor inactivo"},
                status=status.HTTP_200_OK
            )
        except ValueError as e:
            # Capturamos si el servicio rechaza la acción
            return Response(
                {"estado": "error", "mensaje": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class CuentaPorPagarViewSet(viewsets.ModelViewSet):
    """
    Cuentas por pagar a proveedores -- se crean solas desde una compra con
    proveedor (ver `stock_service.crear_y_aplicar_ajuste`), no se crean a
    mano; de solo lectura + la acción `registrar-pago` para abonarlas.
    """
    queryset = CuentaPorPagar.objects.select_related('proveedor').prefetch_related('pagos')
    serializer_class = CuentaPorPagarSerializer
    permission_classes = [IsAdminOrAlmacenista]
    http_method_names = ['get', 'head', 'options', 'post']

    def get_queryset(self):
        qs = super().get_queryset()
        proveedor_id = self.request.query_params.get('proveedor')
        if proveedor_id:
            qs = qs.filter(proveedor_id=proveedor_id)
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def create(self, request, *args, **kwargs):
        return Response({"error": "Las cuentas por pagar se crean automáticamente desde una compra con proveedor."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=['post'], url_path='registrar-pago')
    def registrar_pago(self, request, pk=None):
        cuenta = self.get_object()
        serializer = RegistrarPagoProveedorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            registrar_pago_proveedor(
                cuenta_id=cuenta.id,
                monto=serializer.validated_data['monto'],
                metodo_pago_id=serializer.validated_data.get('metodo_pago_id'),
                referencia=serializer.validated_data.get('referencia', ''),
                usuario=request.user,
            )
        except CuentaPorPagarError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        cuenta.refresh_from_db()
        return Response(self.get_serializer(cuenta).data)


class ReporteCuentasPorPagarView(APIView):
    permission_classes = [IsAdminOrAlmacenista]

    def get(self, request):
        return Response(reporte_cuentas_por_pagar())


class OrdenCompraViewSet(viewsets.ModelViewSet):
    """
    Órdenes de compra a proveedores: se crean en borrador, se marcan
    enviadas, y se reciben (total o parcialmente) línea por línea -- cada
    recepción real aplica una entrada de inventario de siempre (ver
    `compras_service.registrar_recepcion_orden_compra`), así que no hace
    falta editar/borrar una orden ya enviada: se recibe, se cancela si nada
    llegó, o se recibe parcial y se corrige a mano si algo salió mal.
    """
    queryset = OrdenCompra.objects.select_related('proveedor', 'almacen', 'usuario').prefetch_related('detalles__producto')
    serializer_class = OrdenCompraSerializer
    permission_classes = [IsAdminOrAlmacenista]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        proveedor_id = self.request.query_params.get('proveedor')
        if proveedor_id:
            qs = qs.filter(proveedor_id=proveedor_id)
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = CrearOrdenCompraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            orden = crear_orden_compra(
                proveedor_id=data['proveedor_id'],
                almacen_id=data.get('almacen_id'),
                observaciones=data.get('observaciones', ''),
                usuario=request.user,
                detalles_data=[
                    {
                        'producto_id': d['producto_id'], 'cantidad': d['cantidad'],
                        'costo_unitario_esperado': d.get('costo_unitario_esperado'),
                    }
                    for d in data['detalles']
                ],
            )
        except OrdenCompraError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(orden).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def enviar(self, request, pk=None):
        orden = self.get_object()
        try:
            enviar_orden_compra(orden)
        except OrdenCompraError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(orden).data)

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        orden = self.get_object()
        try:
            cancelar_orden_compra(orden)
        except OrdenCompraError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(orden).data)

    @action(detail=True, methods=['post'])
    def recibir(self, request, pk=None):
        orden = self.get_object()
        serializer = RegistrarRecepcionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            registrar_recepcion_orden_compra(
                orden=orden,
                numero_documento=data.get('numero_documento', ''),
                usuario=request.user,
                lineas_recibidas=[
                    {'detalle_id': l['detalle_id'], 'cantidad': l['cantidad'], 'costo_unitario': l.get('costo_unitario')}
                    for l in data['lineas']
                ],
            )
        except OrdenCompraError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        orden.refresh_from_db()
        return Response(self.get_serializer(orden).data)