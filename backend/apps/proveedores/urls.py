from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import ProveedorViewSet, CuentaPorPagarViewSet, ReporteCuentasPorPagarView, OrdenCompraViewSet

router = DefaultRouter()
router.register(r'proveedores', ProveedorViewSet, basename='proveedor')
router.register(r'cuentas-por-pagar', CuentaPorPagarViewSet, basename='cuenta-por-pagar')
router.register(r'ordenes-compra', OrdenCompraViewSet, basename='orden-compra')

urlpatterns = [
    path('reportes/cuentas-por-pagar/', ReporteCuentasPorPagarView.as_view(), name='reporte-cuentas-por-pagar'),
    path('', include(router.urls)),
]