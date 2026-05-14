# apps/inventario/api/views_productos.py
from rest_framework import viewsets, permissions
from apps.inventario.models import Producto, Variacionproducto
from apps.inventario.api.serializers import ProductoSerializer, VariacionproductoSerializer
from drf_spectacular.utils import extend_schema

@extend_schema(tags=['Inventario'])
class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.filter(activo=True).order_by("id")
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save()

class VariacionproductoViewSet(viewsets.ModelViewSet):
    queryset = Variacionproducto.objects.all()
    serializer_class = VariacionproductoSerializer
    permission_classes = [permissions.IsAuthenticated]