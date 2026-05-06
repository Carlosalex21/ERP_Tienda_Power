from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views_terminal import BarcodeScanView, PagoView, FacturaPendienteView, ResetFacturaView
from .api.views_facturas import FacturaViewSet, AnularFacturaView
from .api.views_impresion import FacturaImprimirView
from .api.views_descuentos import ActualizarDescuentoDetalleView, ActualizarDescuentoGlobalView, CupondescuentoViewSet
from .api.views_finanzas import MetodoPagoViewSet, TransaccionpagoViewSet, DevolucionViewSet, TransaccionpagoByMetodo

router = DefaultRouter()
router.register(r'lista', FacturaViewSet, basename='factura')
router.register(r'metodos-pago', MetodoPagoViewSet, basename='metodo-pago')
router.register(r'transacciones', TransaccionpagoViewSet, basename='transaccion')
router.register(r'cupones', CupondescuentoViewSet, basename='cupon')
router.register(r'devoluciones', DevolucionViewSet, basename='devolucion')

urlpatterns = [
    # Facturas
    path("factura/", FacturaList.as_view()),
    path("factura/<int:id>/", FacturaGet.as_view()),
    path("factura/crear/", FacturaCreateUpdateDelete.as_view()),
    path("factura/editar/<int:id>/", FacturaCreateUpdateDelete.as_view()),
    path("factura/eliminar/<int:id>/", FacturaCreateUpdateDelete.as_view()),
    path("factura/<int:pk>/anular/", AnularFacturaView.as_view(), name='anular-factura'),
    path("factura/reset/", ResetFacturaView.as_view()),
    path("factura-pendiente/", FacturaPendienteView.as_view()),
    path("factura-imprimir/<int:factura_id>/", FacturaImprimirView.as_view(), name="factura-imprimir"),
    
    # Descuentos y POS
    path("detallefactura/actualizar-descuento/", ActualizarDescuentoDetalleView.as_view()),
    path("factura/descuento-global/", ActualizarDescuentoGlobalView.as_view()),
    path("barcode-scan/", BarcodeScanView.as_view()),
    
    # Transacciones y Pagos
    path("pago/", PagoView.as_view()),
    path("metodo-pago/", MetodoPagoList.as_view()),
    path("metodo-pago/<int:id>/", MetodoPagoCRUD.as_view()),
    path("metodo-pago/crear/", MetodoPagoCRUD.as_view()),
    path("metodo-pago/editar/<int:id>/", MetodoPagoCRUD.as_view()),
    path("metodo-pago/eliminar/<int:id>/", MetodoPagoCRUD.as_view()),
    path("transaccion-pago/", TransaccionpagoList.as_view()),
    path("transaccion-pago/<int:id>/", TransaccionpagoGet.as_view()),
    path("transaccion-pago/crear/", TransaccionpagoCreateUpdateDelete.as_view()),
    path("transaccion-pago/editar/<int:id>/", TransaccionpagoCreateUpdateDelete.as_view()),
    path("transaccion-pago/eliminar/<int:id>/", TransaccionpagoCreateUpdateDelete.as_view()),
    path("transaccion-metodo/", TransaccionpagoByMetodo.as_view()),
    
    # Cierre de Caja
    path('accounting/cash-closing-report/', CashClosingReportView.as_view(), name='cash-closing-report'),
]