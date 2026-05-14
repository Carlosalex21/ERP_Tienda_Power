from django.contrib import admin
from .models import Proveedor

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'identificador_fiscal', 'email', 'telefono', 'plazo_pago', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'identificador_fiscal', 'email')