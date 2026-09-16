from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views_terminal import BarcodeScanView, PagoView, FacturaPendienteView, ResetFacturaView
from .api.views_facturas import FacturaViewSet, AnularFacturaView
from .api.views_impresion import FacturaImprimirView, NotaCreditoImprimirView, NotaDebitoImprimirView
from .api.views_caja import AbrirCajaView, CajaActualView, CerrarCajaView, CobrosReportView, HistorialCajaView
from .api.views_descuentos import ActualizarDescuentoDetalleView, ActualizarDescuentoGlobalView, CupondescuentoViewSet
from .api.views_finanzas import MetodoPagoViewSet, TransaccionpagoViewSet, DevolucionViewSet, TransaccionpagoByMetodo
from .api.views_facturas import AnularFacturaView
from .api.views_seniat import (
    LibroCompraVentaViewSet,
    NotaCreditoViewSet,
    NotaDebitoViewSet,
    RetencionViewSet,
)

router = DefaultRouter()
router.register(r'lista', FacturaViewSet, basename='factura')
router.register(r'metodos-pago', MetodoPagoViewSet, basename='metodo-pago')
router.register(r'transacciones', TransaccionpagoViewSet, basename='transaccion')
router.register(r'cupones', CupondescuentoViewSet, basename='cupon')
router.register(r'devoluciones', DevolucionViewSet, basename='devolucion')
router.register(r'notas-credito', NotaCreditoViewSet, basename='nota-credito')
router.register(r'notas-debito', NotaDebitoViewSet, basename='nota-debito')
router.register(r'libro-compra-venta', LibroCompraVentaViewSet, basename='libro-compra-venta')
router.register(r'retenciones', RetencionViewSet, basename='retencion')


urlpatterns = [
    # Router viewsets (Facturas, MetodosPago, Transacciones, etc)
    path('', include(router.urls)),

    # Acciones especiales Facturas
    path("factura/reset/", ResetFacturaView.as_view()),
    path("factura-pendiente/", FacturaPendienteView.as_view()),
    path("factura-imprimir/<int:factura_id>/", FacturaImprimirView.as_view(), name="factura-imprimir"),
    path("nota-credito-imprimir/<int:nota_id>/", NotaCreditoImprimirView.as_view(), name="nota-credito-imprimir"),
    path("nota-debito-imprimir/<int:nota_id>/", NotaDebitoImprimirView.as_view(), name="nota-debito-imprimir"),

    # Turno de caja y reporte de Cobros
    path("caja/actual/", CajaActualView.as_view(), name="caja-actual"),
    path("caja/abrir/", AbrirCajaView.as_view(), name="caja-abrir"),
    path("caja/cerrar/", CerrarCajaView.as_view(), name="caja-cerrar"),
    path("caja/historial/", HistorialCajaView.as_view(), name="caja-historial"),
    path("cobros/", CobrosReportView.as_view(), name="cobros-reporte"),
    path('facturas/<int:pk>/anular/', AnularFacturaView.as_view(), name='anular-factura'),
    
    # Descuentos y POS
    path("detallefactura/actualizar-descuento/", ActualizarDescuentoDetalleView.as_view()),
    path("factura/descuento-global/", ActualizarDescuentoGlobalView.as_view()),
    path("barcode-scan/", BarcodeScanView.as_view()),
    
    # Transacciones y Pagos
    path("pago/", PagoView.as_view()),
    path("transaccion-metodo/", TransaccionpagoByMetodo.as_view()),
]
# Nota: los endpoints públicos (catálogo, pedidos) viven en
# apps.catalogo_publico, montados en /api/v1/public/ -- ver backend/urls_tenants.py.
