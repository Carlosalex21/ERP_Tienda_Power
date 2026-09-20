from django.contrib import admin
from .models import Mesa, PedidoMesa, PedidoMesaItem


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'capacidad', 'activo')
    search_fields = ('numero',)


class PedidoMesaItemInline(admin.TabularInline):
    model = PedidoMesaItem
    extra = 0


@admin.register(PedidoMesa)
class PedidoMesaAdmin(admin.ModelAdmin):
    list_display = ('mesa', 'estado', 'mesero', 'fecha_apertura', 'fecha_cierre')
    list_filter = ('estado',)
    inlines = [PedidoMesaItemInline]
