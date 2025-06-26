from django.contrib import admin
from .models import UserMetadata, Rol,Tipodocumentofiscal

@admin.register(UserMetadata)
class UserMetadataAdmin(admin.ModelAdmin):
    list_display = ('user', 'nombre', 'apellido', 'correo', 'rol', 'es_activo', 'verificado')
    search_fields = ('user__username', 'nombre', 'apellido', 'correo')
    list_filter = ('rol', 'es_activo', 'verificado')

admin.site.register(Rol)
admin.site.register(Tipodocumentofiscal)