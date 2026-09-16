# apps/inventario/api/views_ajustes.py
from rest_framework import viewsets

from apps.core.permissions import IsAdminOrAlmacenista
from apps.inventario.models import AjusteInventario
from apps.inventario.api.serializers_ajustes import AjusteInventarioSerializer


class AjusteInventarioViewSet(viewsets.ModelViewSet):
    """
    Ajustes manuales de entrada/salida de stock (notas de entrega sin
    factura, correcciones de conteo físico, mermas, etc.).

    Un ajuste, igual que una factura confirmada, no se edita ni se borra una
    vez creado -- ya movió stock real. Para corregir un error se registra un
    nuevo ajuste en sentido contrario, no se modifica el original.
    """
    http_method_names = ['get', 'post', 'head', 'options']
    queryset = AjusteInventario.objects.select_related(
        'almacen', 'proveedor', 'usuario',
    ).prefetch_related('detalles__producto', 'detalles__variante').all()
    serializer_class = AjusteInventarioSerializer
    permission_classes = [IsAdminOrAlmacenista]
    filterset_fields = ['tipo', 'motivo', 'almacen', 'proveedor']
