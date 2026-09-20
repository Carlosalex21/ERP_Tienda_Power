from django.contrib import admin

from .models import EmpresaContable, CuentaContable, AsientoContable, AsientoContableDetalle


class AsientoContableDetalleInline(admin.TabularInline):
    model = AsientoContableDetalle
    extra = 0


@admin.register(EmpresaContable)
class EmpresaContableAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'identificacion_fiscal', 'cliente', 'activo')
    search_fields = ('nombre', 'identificacion_fiscal')


@admin.register(CuentaContable)
class CuentaContableAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'empresa', 'tipo', 'naturaleza', 'acepta_movimiento', 'activo')
    list_filter = ('empresa', 'tipo')
    search_fields = ('codigo', 'nombre')


@admin.register(AsientoContable)
class AsientoContableAdmin(admin.ModelAdmin):
    list_display = ('numero', 'empresa', 'fecha', 'descripcion', 'estado')
    list_filter = ('empresa', 'estado')
    inlines = [AsientoContableDetalleInline]
