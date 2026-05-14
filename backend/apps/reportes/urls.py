from django.urls import path
from .api.views_clientes import ReporteclienteView
from .api.views_ventas import ReporteventaView, FacturaDetalleReporteView, CashClosingReportView
from .api.views_dashboard import DashboardDataView

urlpatterns = [
    path('clientes/', ReporteclienteView.as_view(), name='reporte-clientes'),
    path('ventas/', ReporteventaView.as_view(), name='reporte-ventas'),
    path('ventas/detalles/', FacturaDetalleReporteView.as_view(), name='reporte-ventas-detalles'),
    path('cierre-caja/', CashClosingReportView.as_view(), name='cierre-caja'),
    path('dashboard/', DashboardDataView.as_view(), name='dashboard-data'),
]

