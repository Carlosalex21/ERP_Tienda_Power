from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    AttendanceSummaryView, ClockInView, ClockOutView, BreakView,
    HorarioDetailView, DiaFestivoListView, DiaFestivoDetailView,
    SucursalViewSet, DepartamentoViewSet, PeriodoNominaViewSet, ConceptoNominaViewSet,
)
from .api.views_impresion import ReciboNominaImprimirView

router = DefaultRouter()
router.register(r'sucursales', SucursalViewSet, basename='sucursal')
router.register(r'departamentos', DepartamentoViewSet, basename='departamento')
router.register(r'nomina', PeriodoNominaViewSet, basename='periodo-nomina')
router.register(r'conceptos-nomina', ConceptoNominaViewSet, basename='concepto-nomina')

urlpatterns = [
    path("attendance-summary/", AttendanceSummaryView.as_view(), name='attendance-summary'),
    path("clock-in/", ClockInView.as_view(), name='clock-in'),
    path("clock-out/", ClockOutView.as_view(), name='clock-out'),
    path("break/", BreakView.as_view(), name='break'),
    path('horario/', HorarioDetailView.as_view(), name='horario-detail'),
    path('dias-festivos/', DiaFestivoListView.as_view(), name='dias-festivos-list'),
    path('dias-festivos/<int:pk>/', DiaFestivoDetailView.as_view(), name='dias-festivos-detail'),
    path('recibo-nomina/<int:nomina_empleado_id>/', ReciboNominaImprimirView.as_view(), name='recibo-nomina-imprimir'),
    path('', include(router.urls)),
]