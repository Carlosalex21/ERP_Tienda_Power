from django.urls import path
# from .views import *

urlpatterns = [
    path("attendance-summary/", AttendanceSummaryView.as_view(), name='attendance-summary'),
    path("clock-in/", ClockInView.as_view(), name='clock-in'),
    path("clock-out/", ClockOutView.as_view(), name='clock-out'),
    path("break/", BreakView.as_view(), name='break'),
    path('horarios/', HorarioDetailView.as_view(), name='horario-create'),
    path('horarios/<int:pk>/', HorarioDetailView.as_view(), name='horario-detail'),
    path('dias-festivos/', DiaFestivoListView.as_view(), name='dias-festivos-list'),
    path('dias-festivos/<int:pk>/', DiaFestivoDetailView.as_view(), name='dias-festivos-detail'),
]