from django.contrib import admin
from .models import Horario, DiaFestivo, Asistencia, Descanso

@admin.register(Horario)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'hora_entrada_oficial', 'hora_salida_oficial', 'margen_tardanza_minutos')
    search_fields = ('nombre',)

@admin.register(DiaFestivo)
class DiaFestivoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'descripcion')
    search_fields = ('descripcion',)
    list_filter = ('fecha',)

@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'fecha', 'hora_entrada', 'hora_salida', 'estado', 'estado_actual', 'llegada_tarde')
    list_filter = ('estado', 'estado_actual', 'llegada_tarde', 'fecha')
    search_fields = ('usuario__username', 'usuario__first_name', 'usuario__last_name')

@admin.register(Descanso)
class DescansoAdmin(admin.ModelAdmin):
    list_display = ('asistencia', 'inicio_descanso', 'fin_descanso')
    list_filter = ('inicio_descanso',)
    search_fields = ('asistencia__usuario__username',)
