# apps/proveedores/api/views.py
from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrVendedor, IsAdminOrAlmacenista, ROL_ADMIN, codigo_rol
from apps.facturacion.services.retencion_service import RetencionServiceError
from apps.inventario.api.almacen_operativo import resolver_almacen_operativo
from apps.proveedores.models import Proveedor, CuentaPorPagar, OrdenCompra, FacturaCompra
from apps.proveedores.api.serializers import (
    ProveedorSerializer, CuentaPorPagarSerializer, RegistrarPagoProveedorSerializer,
    OrdenCompraSerializer, CrearOrdenCompraSerializer, FacturaCompraSerializer, CrearFacturaCompraSerializer,
)
from apps.proveedores.core.proveedores_service import (
    desactivar_proveedor_service, registrar_pago_proveedor, reporte_cuentas_por_pagar,
    CuentaPorPagarError,
)
from apps.proveedores.core.compras_service import (
    crear_orden_compra, enviar_orden_compra, cancelar_orden_compra,
    OrdenCompraError,
)
from apps.proveedores.core.facturas_compra_service import (
    FacturaCompraError, anular_factura_compra, registrar_factura_compra,
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
    Cuentas por pagar a proveedores -- se crean solas al registrar una
    factura de compra (ver `facturas_compra_service`), no se crean a mano;
    de solo lectura + la acción `registrar-pago` para abonarlas.
    """
    queryset = CuentaPorPagar.objects.select_related('proveedor', 'factura_compra').prefetch_related('pagos')
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
    enviadas, y se reciben (total o parcialmente) registrando la factura de
    compra con la que llega la mercancía (`FacturaCompraViewSet` con
    `orden_compra_id`) -- no hace falta editar/borrar una orden ya enviada:
    se recibe, se cancela si nada llegó, o queda parcial.
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



class FacturaCompraViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Compras a proveedores (factura fiscal o nota de entrega). Crear una
    mueve inventario, crea la cuenta por pagar, la asienta y la registra en
    el Libro de Compras (ver `facturas_compra_service`). No se editan: si se
    cargó mal, se anula (`anular`) y se vuelve a cargar.
    """
    serializer_class = FacturaCompraSerializer
    permission_classes = [IsAdminOrAlmacenista]

    def get_queryset(self):
        qs = FacturaCompra.objects.select_related(
            'proveedor', 'almacen', 'orden_compra', 'usuario',
        ).prefetch_related('detalles__producto', 'detalles__variante', 'cuentas_por_pagar')
        params = self.request.query_params
        if params.get('proveedor'):
            qs = qs.filter(proveedor_id=params['proveedor'])
        if params.get('estado'):
            qs = qs.filter(estado=params['estado'])
        if params.get('tipo_documento'):
            qs = qs.filter(tipo_documento=params['tipo_documento'])
        if params.get('fecha_desde'):
            qs = qs.filter(fecha_emision__gte=params['fecha_desde'])
        if params.get('fecha_hasta'):
            qs = qs.filter(fecha_emision__lte=params['fecha_hasta'])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = CrearFacturaCompraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        almacen = data['almacen']
        if data['detalles']:
            almacen = resolver_almacen_operativo(
                request.user, almacen or (data['orden_compra'].almacen if data['orden_compra'] else None),
            )
        try:
            factura = registrar_factura_compra(
                usuario=request.user,
                proveedor=data['proveedor'],
                tipo_documento=data['tipo_documento'],
                numero_factura=data['numero_factura'],
                numero_control=data['numero_control'],
                fecha_emision=data['fecha_emision'],
                almacen=almacen,
                orden_compra=data['orden_compra'],
                detalles=data['detalles'],
                monto_exento=data['monto_exento'],
                base_imponible=data['base_imponible'],
                porcentaje_iva=data['porcentaje_iva'],
                porcentaje_retencion_iva=data['porcentaje_retencion_iva'],
                observaciones=data['observaciones'],
            )
        except (FacturaCompraError, RetencionServiceError) as exc:
            raise serializers.ValidationError({'detail': str(exc)})
        return Response(self.get_serializer(self.get_queryset().get(pk=factura.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        if codigo_rol(getattr(getattr(request.user, 'metadata', None), 'rol', None)) != ROL_ADMIN:
            return Response({"error": "Solo un administrador puede anular una compra."}, status=status.HTTP_403_FORBIDDEN)
        try:
            anular_factura_compra(self.get_object(), usuario=request.user)
        except FacturaCompraError as exc:
            raise serializers.ValidationError({'detail': str(exc)})
        return Response(self.get_serializer(self.get_queryset().get(pk=pk)).data)