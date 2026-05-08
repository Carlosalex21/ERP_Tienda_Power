from django.contrib import admin
from apps.usuarios.models import UserMetadata, Rol
from apps.configuracion.models import Tipodocumentofiscal

@admin.register(UserMetadata)
class UserMetadataAdmin(admin.ModelAdmin):
    # --- CORRECCIÓN ---
    # Usamos los campos que ahora existen en el modelo y en el usuario relacionado.
    list_display = (
        'get_username', 
        'get_full_name', 
        'rol', 
        'puesto', 
        'get_user_is_active'
    )
    list_filter = ('rol', 'almacen_asignado')
    search_fields = (
        'user__username', 
        'user__first_name', 
        'user__last_name', 
        'puesto'
    )
    
    # Métodos para obtener datos del modelo User relacionado
    @admin.display(description='Usuario', ordering='user__username')
    def get_username(self, obj):
        return obj.user.username

    @admin.display(description='Nombre Completo', ordering='user__first_name')
    def get_full_name(self, obj):
        return obj.user.get_full_name()

    @admin.display(description='Activo', ordering='user__is_active', boolean=True)
    def get_user_is_active(self, obj):
        return obj.user.is_active

@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'activo')
    search_fields = ('nombre',)
    list_filter = ('activo',)
