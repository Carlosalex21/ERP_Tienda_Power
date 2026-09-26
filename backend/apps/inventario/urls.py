from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    views_productos, views_almacen,
    views_taxonomia, views_operaciones, views_stock, views_ajustes, views_traslados
)

router = DefaultRouter()
router.register(r'productos', views_productos.ProductoViewSet)
router.register(r'variantes', views_productos.VariacionproductoViewSet)
router.register(r'presentaciones', views_productos.PresentacionProductoViewSet)
router.register(r'almacenes', views_almacen.AlmacenViewSet)
router.register(r'inventario-fisico', views_almacen.InventarioViewSet)
router.register(r'categorias', views_taxonomia.CategoriaViewSet)
router.register(r'atributos', views_taxonomia.AtributoViewSet)
router.register(r'movimientos', views_operaciones.MovimientoInventarioViewSet)
router.register(r'ajustes', views_ajustes.AjusteInventarioViewSet)
router.register(r'traslados', views_traslados.TrasladoInventarioViewSet)

urlpatterns = [
    # Endpoint especializado para el POS
    path('actual/', views_stock.InventarioActualView.as_view(), name='inventario-actual'),
    # Endpoint para la carga masiva de productos
    path('productos/bulk-upload/', views_productos.ProductoBulkUploadView.as_view(), name='producto-bulk-upload'),
    path('productos/bulk-upload/plantilla/', views_productos.ProductoBulkUploadTemplateView.as_view(), name='producto-bulk-upload-plantilla'),
    # Las URLs del router deben ir al final para que las rutas específicas se resuelvan primero.
    path('', include(router.urls)),
]