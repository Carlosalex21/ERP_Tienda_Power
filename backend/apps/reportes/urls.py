from django.urls import path
from .api.views_dashboard import DashboardDataView
from .api.views_clientes import ReporteclienteView
from .api.views_ventas import ReporteventaView, FacturaDetalleReporteView
from apps.inventario.api.views_stock import InventarioActualView

urlpatterns = [
    path('dashboard/', DashboardDataView.as_view(), name='dashboard-data'),
    path('clientes/', ReporteclienteView.as_view(), name='reporte-clientes'),
    path('inventario/', InventarioActualView.as_view(), name='reporte-inventario'),
    path('ventas/', ReporteventaView.as_view(), name='reporte-ventas'),
    path('facturas-detalle/', FacturaDetalleReporteView.as_view(), name='reporte-facturas-detalle'),
]