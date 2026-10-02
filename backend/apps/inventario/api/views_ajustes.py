# apps/inventario/api/views_ajustes.py
from rest_framework import serializers, viewsets
from rest_framework.response import Response

from apps.core.permissions import IsAdminOrAlmacenista
from apps.inventario.models import AjusteInventario
from apps.inventario.api.almacen_operativo import resolver_almacen_operativo
from apps.inventario.api.serializers_ajustes import AjusteInventarioSerializer, AjusteInventarioEditSerializer
from apps.proveedores.core.proveedores_service import sincronizar_cuenta_por_pagar_desde_ajuste


class AjusteInventarioViewSet(viewsets.ModelViewSet):
    """
    Ajustes manuales de entrada/salida de stock por motivos internos
    (conteo físico, mermas, consumo propio, inventario inicial...). Las
    compras a proveedores van por `FacturaCompraViewSet`.

    El movimiento de stock (`tipo`, `almacen`, `detalles`) NO se edita ni se
    borra una vez aplicado -- para corregirlo se registra un nuevo ajuste en
    sentido contrario, no se modifica el original. La METADATA del
    documento sí es editable (`partial_update`, ver
    `AjusteInventarioEditSerializer`) -- típicamente para corregir la fecha
    real de la nota/factura del proveedor, que es la que toma Cuentas por
    Pagar para calcular vencimiento y antigüedad de saldos.
    """
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    queryset = AjusteInventario.objects.select_related(
        'almacen', 'proveedor', 'usuario',
    ).prefetch_related('detalles__producto', 'detalles__variante').all()
    serializer_class = AjusteInventarioSerializer
    permission_classes = [IsAdminOrAlmacenista]
    filterset_fields = ['tipo', 'motivo', 'almacen', 'proveedor']

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return AjusteInventarioEditSerializer
        return AjusteInventarioSerializer

    def perform_create(self, serializer):
        almacen = resolver_almacen_operativo(self.request.user, serializer.validated_data.get('almacen'))
        serializer.save(almacen=almacen)

    def perform_update(self, serializer):
        # La entrada de una factura de compra toma sus datos de la factura;
        # editarla aquí la dejaría distinta de la factura, el libro y la deuda.
        if serializer.instance.facturas_compra.exists():
            raise serializers.ValidationError({
                'detail': 'Este movimiento lo generó una factura de compra -- corrígelo desde Compras > Facturas de compra.',
            })
        ajuste = serializer.save()
        sincronizar_cuenta_por_pagar_desde_ajuste(ajuste)

    def partial_update(self, request, *args, **kwargs):
        # La respuesta se re-serializa con `AjusteInventarioSerializer` (no
        # el restringido `AjusteInventarioEditSerializer` usado para
        # validar la entrada) -- de lo contrario la respuesta no traería
        # `id`, `tipo_display`, `detalles`, etc., y el frontend no podría
        # ni encontrar la fila que acaba de editar en su listado local, ni
        # refrescar las columnas que dependen de esos campos.
        super().partial_update(request, *args, **kwargs)
        ajuste = self.get_object()
        return Response(AjusteInventarioSerializer(ajuste, context=self.get_serializer_context()).data)
