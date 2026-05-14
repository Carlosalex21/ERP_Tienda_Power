from django.contrib import admin
from .models import Reportecliente, Reporteinventario, Reporteventa

@admin.register(Reportecliente)
class ReporteclienteAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'total_compras', 'cantidad_pedidos', 'producto_mas_comprado')
    search_fields = ('cliente__nombre_empresa',) 

@admin.register(Reporteinventario)
class ReporteinventarioAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'producto', 'almacen', 'stock_inicial', 'stock_final', 'movimientos')
    list_filter = ('fecha', 'almacen')
    search_fields = ('producto__nombre',)

@admin.register(Reporteventa)
class ReporteventaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'almacen', 'total_ventas', 'total_iva', 'total_descuentos', 'cantidad_transacciones')
    list_filter = ('fecha', 'almacen')
