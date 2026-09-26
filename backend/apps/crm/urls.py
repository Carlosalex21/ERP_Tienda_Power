from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.views import OportunidadViewSet, CotizacionViewSet, CotizacionPublicaView

router = DefaultRouter()
router.register(r'oportunidades', OportunidadViewSet, basename='oportunidad')
router.register(r'cotizaciones', CotizacionViewSet, basename='cotizacion')

urlpatterns = [
    path('cotizaciones/publica/<str:token>/', CotizacionPublicaView.as_view(), name='cotizacion-publica'),
    path('', include(router.urls)),
]
