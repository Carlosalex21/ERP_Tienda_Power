from django.contrib import admin
from .models import (
    Almacen, Categoriaproducto, Atributo, ValorAtributo, 
    Producto, Productocategoria, Variacionproducto, 
    Inventario, MovimientoInventario, Lecturacodigobarras, 
    Reservastock, Transportista
)

@admin.register(Almacen)
class AlmacenAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'estado', 'telefono', 'activo')
    list_filter = ('estado', 'activo')
    search_fields = ('nombre', 'direccion')

@admin.register(Categoriaproducto)
class CategoriaproductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'padre', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre',)

@admin.register(Atributo)
class AtributoAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(ValorAtributo)
class ValorAtributoAdmin(admin.ModelAdmin):
    list_display = ('valor', 'atributo')
    list_filter = ('atributo',)
    search_fields = ('valor',)

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'sku', 'codigo_barras', 'precio', 'cantidad', 'tipo', 'activo')
    list_filter = ('tipo', 'activo', 'disponible_online')
    search_fields = ('nombre', 'sku', 'codigo_barras')

@admin.register(Productocategoria)
class ProductocategoriaAdmin(admin.ModelAdmin):
    list_display = ('producto', 'categoria')
    list_filter = ('categoria',)
    search_fields = ('producto__nombre', 'categoria__nombre')

@admin.register(Variacionproducto)
class VariacionproductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'producto', 'sku', 'precio', 'cantidad')
    search_fields = ('nombre', 'sku', 'producto__nombre')

@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = ('producto', 'almacen', 'cantidad', 'activo')
    list_filter = ('almacen', 'activo')
    search_fields = ('producto__nombre',)

@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ('inventario', 'tipo_movimiento', 'cantidad', 'fecha_movimiento', 'activo')
    list_filter = ('tipo_movimiento', 'activo', 'fecha_movimiento')
    search_fields = ('inventario__producto__nombre',)

@admin.register(Lecturacodigobarras)
class LecturacodigobarrasAdmin(admin.ModelAdmin):
    list_display = ('codigo_barras', 'fecha_lectura', 'almacen')
    list_filter = ('almacen', 'fecha_lectura')
    search_fields = ('codigo_barras',)

@admin.register(Reservastock)
class ReservastockAdmin(admin.ModelAdmin):
    list_display = ('producto', 'almacen', 'cantidad', 'orden', 'valido_hasta')
    list_filter = ('almacen', 'valido_hasta')
    search_fields = ('producto__nombre', 'orden__id')

@admin.register(Transportista)
class TransportistaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo_envio', 'precio_base', 'tiempo_entrega', 'activo')
    list_filter = ('activo', 'tipo_envio')
    search_fields = ('nombre',)