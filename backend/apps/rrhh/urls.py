from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    AttendanceSummaryView, ClockInView, ClockOutView, BreakView,
    HorarioDetailView, DiaFestivoListView, DiaFestivoDetailView,
    SucursalViewSet, DepartamentoViewSet, PeriodoNominaViewSet, ConceptoNominaViewSet,
    NominaEmpleadoViewSet, ConfiguracionRRHHView, VacacionesEmpleadoView, VacacionTomadaDetailView,
    LiquidacionCalculadoraView,
)
from .api.views_impresion import ReciboNominaImprimirView

router = DefaultRouter()
router.register(r'sucursales', SucursalViewSet, basename='sucursal')
router.register(r'departamentos', DepartamentoViewSet, basename='departamento')
router.register(r'nomina', PeriodoNominaViewSet, basename='periodo-nomina')
router.register(r'conceptos-nomina', ConceptoNominaViewSet, basename='concepto-nomina')
router.register(r'nomina-empleados', NominaEmpleadoViewSet, basename='nomina-empleado')

urlpatterns = [
    path("attendance-summary/", AttendanceSummaryView.as_view(), name='attendance-summary'),
    path("clock-in/", ClockInView.as_view(), name='clock-in'),
    path("clock-out/", ClockOutView.as_view(), name='clock-out'),
    path("break/", BreakView.as_view(), name='break'),
    path('horario/', HorarioDetailView.as_view(), name='horario-detail'),
    path('dias-festivos/', DiaFestivoListView.as_view(), name='dias-festivos-list'),
    path('dias-festivos/<int:pk>/', DiaFestivoDetailView.as_view(), name='dias-festivos-detail'),
    path('recibo-nomina/<int:nomina_empleado_id>/', ReciboNominaImprimirView.as_view(), name='recibo-nomina-imprimir'),
    path('configuracion-rrhh/', ConfiguracionRRHHView.as_view(), name='configuracion-rrhh'),
    path('vacaciones/<int:usuario_id>/', VacacionesEmpleadoView.as_view(), name='vacaciones-empleado'),
    path('vacaciones-tomadas/<int:vacacion_id>/', VacacionTomadaDetailView.as_view(), name='vacacion-tomada-detail'),
    path('liquidacion/<int:usuario_id>/', LiquidacionCalculadoraView.as_view(), name='liquidacion-calculadora'),
    path('', include(router.urls)),
]