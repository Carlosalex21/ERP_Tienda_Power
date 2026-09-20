from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.views import OrdenServicioViewSet, OrdenServicioPublicoView

router = DefaultRouter()
router.register(r'ordenes', OrdenServicioViewSet, basename='orden-servicio')

urlpatterns = [
    path('', include(router.urls)),
    path('publico/<str:token>/', OrdenServicioPublicoView.as_view(), name='orden-servicio-publica'),
]
