from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    views_productos, views_almacen, 
    views_taxonomia, views_operaciones, views_stock
)

router = DefaultRouter()
router.register(r'productos', views_productos.ProductoViewSet)
router.register(r'variantes', views_productos.VariacionproductoViewSet)
router.register(r'almacenes', views_almacen.AlmacenViewSet)
router.register(r'inventario-fisico', views_almacen.InventarioViewSet)
router.register(r'categorias', views_taxonomia.CategoriaViewSet)
router.register(r'atributos', views_taxonomia.AtributoViewSet)
router.register(r'movimientos', views_operaciones.MovimientoInventarioViewSet)

urlpatterns = [
    path('', include(router.urls)),
    # Endpoint especializado para el POS
    path('actual/', views_stock.InventarioActualView.as_view(), name='inventario-actual'),
]