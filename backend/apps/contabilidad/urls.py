from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api.views import (
    EmpresaContableViewSet, CuentaContableViewSet, AsientoContableViewSet, AsientoPlantillaViewSet,
    LibroMayorView, BalanceComprobacionView, EstadosFinancierosView, ConciliacionBancariaView,
    BalanceComprobacionExportView, EstadosFinancierosExportView, LibroMayorExportView,
    MiEmpresaContableView,
)

router = DefaultRouter()
router.register(r'empresas', EmpresaContableViewSet, basename='empresa-contable')
router.register(r'cuentas', CuentaContableViewSet, basename='cuenta-contable')
router.register(r'asientos', AsientoContableViewSet, basename='asiento-contable')
router.register(r'plantillas', AsientoPlantillaViewSet, basename='asiento-plantilla')

urlpatterns = [
    path('mi-empresa/', MiEmpresaContableView.as_view(), name='mi-empresa-contable'),
    path('', include(router.urls)),
    path('reportes/libro-mayor/', LibroMayorView.as_view(), name='libro-mayor'),
    path('reportes/balance-comprobacion/', BalanceComprobacionView.as_view(), name='balance-comprobacion'),
    path('reportes/estados-financieros/', EstadosFinancierosView.as_view(), name='estados-financieros'),
    path('reportes/libro-mayor/exportar/', LibroMayorExportView.as_view(), name='libro-mayor-exportar'),
    path('reportes/balance-comprobacion/exportar/', BalanceComprobacionExportView.as_view(), name='balance-comprobacion-exportar'),
    path('reportes/estados-financieros/exportar/', EstadosFinancierosExportView.as_view(), name='estados-financieros-exportar'),
    path('conciliacion-bancaria/', ConciliacionBancariaView.as_view(), name='conciliacion-bancaria'),
]
