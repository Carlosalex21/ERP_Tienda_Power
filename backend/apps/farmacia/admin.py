from django.contrib import admin
from .models import LoteProducto


@admin.register(LoteProducto)
class LoteProductoAdmin(admin.ModelAdmin):
    list_display = ('producto', 'numero_lote', 'fecha_vencimiento', 'cantidad', 'activo')
    list_filter = ('activo',)
    search_fields = ('producto__nombre', 'numero_lote')
