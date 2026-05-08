# apps/inventario/api/views_almacen.py
from rest_framework import viewsets, permissions
from apps.inventario.models import Almacen, Inventario
from apps.inventario.api.serializers import AlmacenSerializer, InventarioSerializer

class AlmacenViewSet(viewsets.ModelViewSet):
    queryset = Almacen.objects.filter(activo=True).order_by("id")
    serializer_class = AlmacenSerializer
    permission_classes = [permissions.IsAuthenticated]

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