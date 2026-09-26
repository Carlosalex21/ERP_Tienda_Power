from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.views import GarantiaViewSet, ReclamoPostventaViewSet

router = DefaultRouter()
router.register(r'garantias', GarantiaViewSet, basename='garantia')
router.register(r'reclamos', ReclamoPostventaViewSet, basename='reclamo-postventa')

urlpatterns = [
    path('', include(router.urls)),
]
