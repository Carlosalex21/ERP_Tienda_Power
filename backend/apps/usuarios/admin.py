from django.contrib import admin
from .models import UserMetadata, Rol

@admin.register(UserMetadata)
class UserMetadataAdmin(admin.ModelAdmin):
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