from django.contrib import admin
from .models import OrdenServicio


@admin.register(OrdenServicio)
class OrdenServicioAdmin(admin.ModelAdmin):
    list_display = ('numero', 'cliente', 'equipo', 'estado', 'tecnico', 'fecha_recepcion')
    list_filter = ('estado',)
    search_fields = ('numero', 'equipo', 'cliente__nombre')
