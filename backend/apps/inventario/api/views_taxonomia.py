# apps/inventario/api/views_taxonomia.py
from rest_framework import viewsets, permissions
from apps.inventario.models import Categoriaproducto, Productocategoria, Atributo
from apps.inventario.api.serializers import CategoriaSerializer, ProductocategoriaSerializer, AtributoSerializer

class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoriaproducto.objects.filter(activo=True).order_by("id")
    serializer_class = CategoriaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save()

class ProductocategoriaViewSet(viewsets.ModelViewSet):
    queryset = Productocategoria.objects.all().order_by("id")
    serializer_class = ProductocategoriaSerializer
    permission_classes = [permissions.IsAuthenticated]

class AtributoViewSet(viewsets.ModelViewSet):
    queryset = Atributo.objects.prefetch_related('valores').all()
    serializer_class = AtributoSerializer
    permission_classes = [permissions.IsAuthenticated]