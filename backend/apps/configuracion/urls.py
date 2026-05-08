from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import IvaViewSet, TipoDocumentoViewSet

router = DefaultRouter()
router.register(r'iva', IvaViewSet, basename='iva')
router.register(r'tipos-documento', TipoDocumentoViewSet, basename='tipos-documento')

urlpatterns = [
    path('', include(router.urls)),
]