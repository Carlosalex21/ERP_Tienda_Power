from rest_framework import viewsets, permissions
from erp.models import Orden
from erp.serializers import OrdenSerializer

class OrdenViewSet(viewsets.ModelViewSet):
    """Maneja el CRUD de Órdenes/Pedidos antes de ser facturados."""
    queryset = Orden.objects.filter(activo=True).order_by("-fecha_creacion")
    serializer_class = OrdenSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save()