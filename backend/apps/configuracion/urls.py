from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    IvaViewSet,
    MonedaViewSet,
    TasaCambioViewSet,
    TasaCambioActualView,
    TaxStrategyView,
    TipoDocumentoViewSet,
    ConfiguracionEmpresaView,
)

router = DefaultRouter()
router.register(r"iva", IvaViewSet, basename="iva")
router.register(r"tipos-documento", TipoDocumentoViewSet, basename="tipos-documento")
router.register(r"monedas", MonedaViewSet, basename="moneda")
router.register(r"tasas-cambio", TasaCambioViewSet, basename="tasa-cambio")

urlpatterns = [
    path("empresa/", ConfiguracionEmpresaView.as_view(), name="configuracion-empresa"),
    path("tax-strategy/", TaxStrategyView.as_view(), name="tax-strategy"),
    path("tasas-cambio/actual/", TasaCambioActualView.as_view(), name="tasas-cambio-actual"),
    path("", include(router.urls)),
]
