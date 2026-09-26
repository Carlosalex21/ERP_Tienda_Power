# apps/inventario/api/views_almacen.py
from rest_framework import viewsets, permissions
from apps.core.permissions import IsTenantAdmin
from apps.inventario.models import Almacen, Inventario
from apps.inventario.api.serializers import AlmacenSerializer, InventarioSerializer

class AlmacenViewSet(viewsets.ModelViewSet):
    queryset = Almacen.objects.filter(activo=True).order_by("id")
    serializer_class = AlmacenSerializer
    # Gestión de sucursales/almacenes -- ya aplica el límite del plan
    # pagado (`perform_create` abajo) igual que `UserManagementViewSet`
    # (`limite_usuarios`), que sí es admin-only; esta se quedó abierta a
    # cualquier empleado, que podía agotar el cupo de sucursales del plan.
    permission_classes = [IsTenantAdmin]

    def perform_create(self, serializer):
        from apps.core.plan_limits import verificar_limite

        verificar_limite(
            self.request, 'limite_sucursales',
            Almacen.objects.filter(activo=True).count(), 'almacenes/sucursales',
        )
        serializer.save()

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save()

class InventarioViewSet(viewsets.ModelViewSet):
    """
    Desglose de stock por almacén. `filterset_fields`: sin esto,
    `?almacen=<id>` no filtraba nada (el backend de filtros por defecto
    exige que cada ViewSet declare explícitamente qué campos admite) -- el
    selector de traslados necesita justo esto para mostrar "qué hay
    disponible en el almacén de origen elegido".
    """
    queryset = Inventario.objects.select_related('producto', 'almacen').filter(activo=True).order_by("id")
    serializer_class = InventarioSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['almacen', 'producto']

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save()