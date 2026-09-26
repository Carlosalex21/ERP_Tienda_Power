# apps/inventario/api/views_traslados.py
from rest_framework import viewsets

from apps.core.permissions import IsAdminOrAlmacenista
from apps.inventario.models import TrasladoInventario
from apps.inventario.api.serializers_traslados import TrasladoInventarioSerializer


class TrasladoInventarioViewSet(viewsets.ModelViewSet):
    """
    Traslados de stock entre almacenes -- directos e inmediatos (ver
    docstring de `TrasladoInventario`), no editables ni borrables una vez
    creados (ya movieron stock real; para corregir un error se hace un
    traslado en sentido contrario, mismo criterio que los Ajustes).

    El desglose de "cuánto hay en cada almacén" para armar el selector de
    origen vive en `InventarioViewSet` (`/inventario-fisico/?almacen=<id>`),
    no aquí.
    """
    http_method_names = ['get', 'post', 'head', 'options']
    queryset = TrasladoInventario.objects.select_related(
        'almacen_origen', 'almacen_destino', 'usuario',
    ).prefetch_related('detalles__producto').all()
    serializer_class = TrasladoInventarioSerializer
    permission_classes = [IsAdminOrAlmacenista]
    filterset_fields = ['almacen_origen', 'almacen_destino']
