# apps/inventario/api/views_ajustes.py
from rest_framework import serializers, viewsets
from rest_framework.response import Response

from apps.core.permissions import IsAdminOrAlmacenista, ROL_ADMIN, codigo_rol
from apps.inventario.models import AjusteInventario, Almacen
from apps.inventario.api.serializers_ajustes import AjusteInventarioSerializer, AjusteInventarioEditSerializer
from apps.proveedores.core.proveedores_service import sincronizar_cuenta_por_pagar_desde_ajuste


class AjusteInventarioViewSet(viewsets.ModelViewSet):
    """
    Ajustes manuales de entrada/salida de stock (notas de entrega sin
    factura, correcciones de conteo físico, mermas, etc.).

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
        # En qué almacén entra/sale la mercancía:
        # - Un administrador elige cualquiera.
        # - Cualquier otro rol (almacenista) queda atado a su almacén
        #   operativo (`UserMetadata.almacen_asignado`) -- no puede cargarle
        #   stock a otra sucursal, aunque mande otro id.
        # - Sin almacén indicado se asume el del empleado; si el tenant tiene
        #   uno solo, ese. Con varios y sin forma de saberlo, se pide
        #   explícitamente en vez de dejar el ajuste "sin sucursal".
        metadata = getattr(self.request.user, 'metadata', None)
        es_admin = bool(metadata) and codigo_rol(metadata.rol) == ROL_ADMIN
        almacen_propio = getattr(metadata, 'almacen_asignado', None)
        almacen = serializer.validated_data.get('almacen')

        if not es_admin and almacen_propio is not None:
            if almacen is not None and almacen.pk != almacen_propio.pk:
                raise serializers.ValidationError({
                    'almacen': f'Solo puedes registrar ajustes en tu almacén asignado ({almacen_propio.nombre}).',
                })
            almacen = almacen_propio

        if almacen is None:
            almacen = almacen_propio
        if almacen is None:
            activos = list(Almacen.objects.filter(activo=True)[:2])
            if len(activos) == 1:
                almacen = activos[0]
            elif len(activos) > 1:
                raise serializers.ValidationError({'almacen': 'Indica en qué almacén entra o sale esta mercancía.'})

        serializer.save(almacen=almacen)

    def perform_update(self, serializer):
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
