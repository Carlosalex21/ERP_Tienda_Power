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
    queryset = Inventario.objects.filter(activo=True).order_by("id")
    serializer_class = InventarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save()