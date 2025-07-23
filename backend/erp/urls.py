from django.urls import path
from .views import *
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenVerifyView)

urlpatterns = [
    #Dashboard
    path('api/dashboard/', DashboardDataView.as_view(), name='dashboard-data'),
    #Login y usuarios
    path('api/usuarios/', UserMetadataListCreateView.as_view(), name='usuarios-list-create'),
    path('api/usuarios/<int:pk>/', UserMetadataDetailView.as_view(), name='usuarios-detail'),
    path('api/tipos-documento/', TipodocumentofiscalList.as_view(), name='tipos-documentos'),
    path('api/roles/', RolList.as_view(), name='roles'),
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    #Productos
    path("api/producto", ProductoList.as_view()),
    path("api/producto/<int:id>/", ProductoGet.as_view()),
    path("api/producto/crear", ProductoCreateUpdateDelete.as_view()),
    path("api/producto/editar/<int:id>", ProductoCreateUpdateDelete.as_view()),
    path("api/producto/eliminar/<int:id>", ProductoCreateUpdateDelete.as_view()),
    #Atributo Producto get y post
    path("api/variante-producto", VariacionproductoListCreateView.as_view()),
    #Get, PUT, PATCH, DELETE
    path("api/variante-producto/<int:pk>", VariacionproductoDetailView.as_view()),
    # Atributos
    path("api/atributo", AtributoListCreateView.as_view()),
    path("api/atributo/<int:pk>", AtributoDetailView.as_view()),

    # Valores de atributo
    path("api/valor-atributo", ValorAtributoListCreateView.as_view()),
    path("api/valor-atributo/<int:pk>", ValorAtributoDetailView.as_view()),
    #Almacen
    path("api/almacen", AlmacenList.as_view()),
    path("api/almacen/<int:id>", AlmacenGet.as_view()),
    path("api/almacen/crear", AlmacenCRUD.as_view()),
    path("api/almacen/editar/<int:id>", AlmacenCRUD.as_view()),
    path("api/almacen/eliminar/<int:id>", AlmacenCRUD.as_view()),
    #Inventario
    path("api/inventario", InventarioList.as_view()),
    path("api/inventario/<int:id>", InventarioGet.as_view()),
    path("api/inventario/crear", InventarioCrud.as_view()),
    path("api/inventario/editar/<int:id>", InventarioCrud.as_view()),
    path("api/inventario/eliminar/<int:id>", InventarioCrud.as_view()),
    #Configuracion IVA
    path("api/configuracion-iva", ConfiguracionivaList.as_view()),
    path("api/configuracion-iva/<int:id>", ConfiguracionivaGet.as_view()),
    path("api/configuracion-iva/crear", ConfiguracionivaCRUD.as_view()),
    path("api/configuracion-iva/editar/<int:id>", ConfiguracionivaCRUD.as_view()),
    path("api/configuracion-iva/eliminar/<int:id>", ConfiguracionivaCRUD.as_view()),
    #tabla categoria Producto
    path("api/categoria", CategoriaList.as_view()),
    path("api/categoria/<int:id>", CategoriaGet.as_view()),
    path("api/categoria/crear", CategoriaCrud.as_view()),
    path("api/categoria/editar/<int:id>", CategoriaCrud.as_view()),
    path("api/categoria/eliminar/<int:id>", CategoriaCrud.as_view()),
    #tabla Cliente
    path("api/cliente", ClienteList.as_view()),
    path("api/cliente/<int:id>", ObtenerclienteAPIView.as_view()),
    path("api/cliente/crear", ClienteCreateUpdateDelete.as_view()),
    path("api/cliente/editar/<int:id>", ClienteCreateUpdateDelete.as_view()),
    path("api/cliente/eliminar/<int:id>", ClienteCreateUpdateDelete.as_view()),
    #Transaccion Pago
    path("api/transaccion-pago", TransaccionpagoList.as_view()),
    path("api/transaccion-pago/<int:id>", TransaccionpagoGet.as_view()),
    path("api/transaccion-pago/crear", TransaccionpagoCreateUpdateDelete.as_view()),
    path("api/transaccion-pago/editar/<int:id>", TransaccionpagoCreateUpdateDelete.as_view()),
    path("api/transaccion-pago/eliminar/<int:id>", TransaccionpagoCreateUpdateDelete.as_view()),
    #Procesar pago pendiente o Pagar Luego
    #path("api/procesar-pago-pendiente", procesar_pago_pendiente),
    #Metodo Pago
    path("api/metodo-pago", MetodoPagoList.as_view()),
    path("api/metodo-pago/<int:id>", MetodoPagoCRUD.as_view()),
    path("api/metodo-pago/crear", MetodoPagoCRUD.as_view()),
    path("api/metodo-pago/editar/<int:id>", MetodoPagoCRUD.as_view()),
    path("api/metodo-pago/eliminar/<int:id>", MetodoPagoCRUD.as_view()),
    #Transacciones por Método de Pago
    path("api/transaccion-metodo", TransaccionpagoByMetodo.as_view()),
    # Api para pagos
    path("api/pago", PagoView.as_view()),
    #API recuperar factura antigua
    path('api/factura-pendiente', FacturaPendienteView.as_view()),
    #Eliminar factura pendiente
    path('api/factura/reset', ResetFacturaView.as_view()),
    #Imprimir factura pdf
     path("api/factura-imprimir/<int:factura_id>", FacturaImprimirView.as_view(), name="factura-imprimir"),
     #Facturas
    path("api/factura", FacturaList.as_view()),
    path("api/factura/<int:id>", FacturaGet.as_view()),
    path("api/factura/crear", FacturaCreateUpdateDelete.as_view()),
    path("api/factura/editar/<int:id>", FacturaCreateUpdateDelete.as_view()),
    path("api/factura/eliminar/<int:id>", FacturaCreateUpdateDelete.as_view()),
    #Actualizar factura con descuento global
    path("api/detallefactura/actualizar-descuento", ActualizarDescuentoDetalleView.as_view()),
    #Actualizar factura con descuento global
    path("api/factura/descuento-global", ActualizarDescuentoGlobalView.as_view()),
    #Logica barcode-scan
    path("api/barcode-scan",BarcodeScanView.as_view()),
    #Configuracion correlativo
    path("api/configuracion/correlativo/", ConfiguracionCorrelativoManageView.as_view()),
    #Reportes
    path('api/reportes/clientes/', ReporteclienteView.as_view(), name='reporte-clientes'),
    path('api/reportes/inventario/', ReporteinventarioView.as_view(), name='reporte-inventario'),
    path('api/reportes/ventas/', ReporteventaView.as_view(), name='reporte-ventas'),
    path('api/reportes/facturas-detalle/', FacturaDetalleReporteView.as_view(), name='reporte-facturas-detalle'),
]
