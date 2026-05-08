from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views_terminal import BarcodeScanView, PagoView, FacturaPendienteView, ResetFacturaView
from .api.views_facturas import FacturaViewSet, AnularFacturaView
from .api.views_impresion import FacturaImprimirView
from .api.views_descuentos import ActualizarDescuentoDetalleView, ActualizarDescuentoGlobalView, CupondescuentoViewSet
from .api.views_finanzas import MetodoPagoViewSet, TransaccionpagoViewSet, DevolucionViewSet, TransaccionpagoByMetodo
from .api.views_public_catalog import PublicCatalogView
from .api.views_external_order import CreateExternalOrderCUD

router = DefaultRouter()
router.register(r'lista', FacturaViewSet, basename='factura')
router.register(r'metodos-pago', MetodoPagoViewSet, basename='metodo-pago')
router.register(r'transacciones', TransaccionpagoViewSet, basename='transaccion')
router.register(r'cupones', CupondescuentoViewSet, basename='cupon')
router.register(r'devoluciones', DevolucionViewSet, basename='devolucion')

urlpatterns = [
    # Router viewsets (Facturas, MetodosPago, Transacciones, etc)
    path('', include(router.urls)),

    # Acciones especiales Facturas
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
    path("transaccion-metodo/", TransaccionpagoByMetodo.as_view()),
    
    # API Pública SaaS
    path("public/catalog/", PublicCatalogView.as_view(), name="public-catalog"),
    path("public/external-order/crear/", CreateExternalOrderCUD.as_view(), name="create-external-order"),
]