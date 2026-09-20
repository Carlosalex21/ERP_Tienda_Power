from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.views import LoteProductoViewSet

router = DefaultRouter()
router.register(r'lotes', LoteProductoViewSet, basename='lote-producto')

urlpatterns = [
    path('', include(router.urls)),
]
