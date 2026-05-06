from django.urls import path
# from .views import *

urlpatterns = [
    path('dashboard/', DashboardDataView.as_view(), name='dashboard-data'),
    path('clientes/', ReporteclienteView.as_view(), name='reporte-clientes'),
    path('inventario/', InventarioActualView.as_view(), name='reporte-inventario'),
    path('ventas/', ReporteventaView.as_view(), name='reporte-ventas'),
    path('facturas-detalle/', FacturaDetalleReporteView.as_view(), name='reporte-facturas-detalle'),
]