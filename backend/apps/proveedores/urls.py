from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import ProveedorViewSet

router = DefaultRouter()
router.register(r'proveedores', ProveedorViewSet, basename='proveedor')

urlpatterns = [
    path('', include(router.urls)),
]