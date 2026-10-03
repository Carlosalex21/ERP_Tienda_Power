from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.inmuebles.api import views, views_publico as publico

router = DefaultRouter()
router.register('edificios', views.EdificioViewSet, basename='edificio')
# Las unidades se exponen bajo dos nombres para poder vender "condominios" e
# "inmobiliaria" como módulos distintos sin que se bloqueen entre sí.
router.register('unidades', views.UnidadViewSet, basename='unidad')
router.register('propiedades', views.UnidadViewSet, basename='propiedad')
router.register('medios-pago', views.MedioPagoViewSet, basename='medio-pago-inmueble')
router.register('gastos-comunes', views.GastoComunViewSet, basename='gasto-comun')
router.register('periodos-condominio', views.PeriodoCondominioViewSet, basename='periodo-condominio')
router.register('cargos', views.CargoViewSet, basename='cargo')
router.register('recibos', views.ReciboViewSet, basename='recibo')
router.register('pagos-reportados', views.PagoReportadoViewSet, basename='pago-reportado')
router.register('contratos', views.ContratoViewSet, basename='contrato')
router.register('gastos-propiedad', views.GastoPropiedadViewSet, basename='gasto-propiedad')
router.register('liquidaciones', views.LiquidacionViewSet, basename='liquidacion')
router.register('consultas', views.ConsultaPropiedadViewSet, basename='consulta-propiedad')

urlpatterns = [
    path('portal-accesos/', views.PortalAccesoView.as_view(), name='portal-acceso'),
    path('reportes/morosidad/', views.ReporteMorosidadView.as_view(), name='reporte-morosidad'),
    path('reportes/recordatorios/', views.RecordatoriosMorosidadView.as_view(), name='reporte-recordatorios'),
    path('reportes/tablero/', views.TableroView.as_view(), name='tablero-inmuebles'),

    # Públicas (sin sesión)
    path('publico/propiedades/', publico.PropiedadesPublicasView.as_view(), name='propiedades-publicas'),
    path('publico/propiedades/filtros/', publico.FiltrosPropiedadesView.as_view(), name='propiedades-filtros'),
    path('publico/propiedades/<int:pk>/', publico.PropiedadPublicaDetalleView.as_view(), name='propiedad-publica'),
    path('publico/consultas/', publico.ConsultaPublicaView.as_view(), name='consulta-publica'),
    path('portal/<str:token>/', publico.PortalDatosView.as_view(), name='portal-datos'),
    path('portal/<str:token>/reportar-pago/', publico.PortalReportarPagoView.as_view(), name='portal-reportar-pago'),
    path('portal/<str:token>/recibo/<int:recibo_id>/pdf/', publico.PortalReciboPdfView.as_view(), name='portal-recibo-pdf'),
    path('portal/<str:token>/unidad/<int:unidad_id>/estado-cuenta/pdf/', publico.PortalEstadoCuentaPdfView.as_view(), name='portal-estado-cuenta-pdf'),
    path('portal/<str:token>/cuota/<int:cargo_id>/pdf/', publico.PortalReciboCondominioPdfView.as_view(), name='portal-cuota-pdf'),

    path('', include(router.urls)),
]
