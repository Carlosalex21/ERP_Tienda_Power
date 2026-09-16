from django.contrib import admin
from .models import (
    MetodoPago, Factura, Facturaelectronica, Cupondescuento,
    Detallefactura, Orden, Devolucion, Direccionenvio,
    Envio, Transaccionpago, Promocion,
    NotaCredito, NotaDebito, LibroCompraVenta, Retencion,
)


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo_metodo', 'nro_cuenta', 'activo')
    list_filter = ('tipo_metodo', 'activo')
    search_fields = ('nombre', 'nro_cuenta')

@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ('id', 'correlativo', 'cliente', 'fecha_operacion', 'total', 'estado', 'activo')
    list_filter = ('estado', 'activo', 'fecha_operacion')
    search_fields = ('correlativo', 'cliente__nombre_empresa', 'nif_factura')

@admin.register(Facturaelectronica)
class FacturaelectronicaAdmin(admin.ModelAdmin):
    list_display = ('factura', 'proveedor_codigo', 'estado', 'fecha_procesado', 'activo')
    list_filter = ('estado', 'proveedor_codigo', 'activo')
    search_fields = ('factura__correlativo', 'csv')

@admin.register(Cupondescuento)
class CupondescuentoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'tipo', 'valor', 'valido_desde', 'valido_hasta', 'usos_actuales')
    list_filter = ('tipo',)
    search_fields = ('codigo',)

@admin.register(Detallefactura)
class DetallefacturaAdmin(admin.ModelAdmin):
    list_display = ('factura', 'producto', 'variante', 'cantidad', 'precio_unitario', 'total_linea')
    search_fields = ('factura__correlativo', 'producto__nombre')

@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ('id', 'correlativo', 'cliente', 'fecha_creacion', 'estado', 'total', 'activo')
    list_filter = ('estado', 'activo', 'fecha_creacion')
    search_fields = ('correlativo', 'cliente__nombre_empresa')

@admin.register(Devolucion)
class DevolucionAdmin(admin.ModelAdmin):
    list_display = ('orden', 'estado', 'monto_reembolso', 'fecha_solicitud', 'activo')
    list_filter = ('estado', 'activo')
    search_fields = ('orden__correlativo', 'motivo')

@admin.register(Direccionenvio)
class DireccionenvioAdmin(admin.ModelAdmin):
    list_display = ('alias', 'cliente', 'provincia', 'codigo_postal', 'predeterminada')
    list_filter = ('provincia', 'predeterminada')
    search_fields = ('alias', 'cliente__nombre_empresa', 'direccion')

@admin.register(Envio)
class EnvioAdmin(admin.ModelAdmin):
    list_display = ('orden', 'transportista', 'numero_seguimiento', 'estado', 'fecha_envio')
    list_filter = ('estado', 'fecha_envio')
    search_fields = ('orden__correlativo', 'numero_seguimiento', 'transportista')

@admin.register(Transaccionpago)
class TransaccionpagoAdmin(admin.ModelAdmin):
    list_display = ('codigo_transaccion', 'orden', 'monto', 'metodo_pago', 'estado', 'fecha')
    list_filter = ('estado', 'metodo_pago')
    search_fields = ('codigo_transaccion', 'orden__correlativo')

@admin.register(Promocion)
class PromocionAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'tipo', 'valor', 'fecha_inicio', 'fecha_fin')
    list_filter = ('tipo', 'fecha_inicio', 'fecha_fin')
    search_fields = ('codigo',)
