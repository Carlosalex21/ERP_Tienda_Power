from django.contrib import admin
from .models import Configuracioniva, Tipodocumentofiscal, ConfiguracionCorrelativo, ConfiguracionEmpresa
from django_tenants.utils import get_public_schema_name

@admin.register(Configuracioniva)
class ConfiguracionivaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'porcentaje_iva', 'activo', 'fecha_creacion')
    list_filter = ('activo',)
    search_fields = ('nombre',)

@admin.register(Tipodocumentofiscal)
class TipodocumentofiscalAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'descripcion', 'obligatorio', 'activo')
    list_filter = ('obligatorio', 'activo')
    search_fields = ('codigo', 'descripcion')

@admin.register(ConfiguracionCorrelativo)
class ConfiguracionCorrelativoAdmin(admin.ModelAdmin):
    list_display = ('prefijo', 'current_number', 'number_length')
    search_fields = ('prefijo',)

@admin.register(ConfiguracionEmpresa)
class ConfiguracionEmpresaAdmin(admin.ModelAdmin):
    """
    Admin para la configuración de la empresa. Solo debe haber una instancia.
    """
    list_display = ('nombre_comercial', 'razon_social', 'rif', 'telefono')

    def has_add_permission(self, request):
        # Si estamos en el esquema público, no se puede agregar desde el admin principal.
        if request.tenant.schema_name == get_public_schema_name():
            return False
        # Dentro de un tenant, solo permite agregar si no existe ya una configuración.
        return not ConfiguracionEmpresa.objects.exists()
