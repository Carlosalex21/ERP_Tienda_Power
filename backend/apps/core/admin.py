from django.contrib import admin
from apps.usuarios.models import Logactividad

@admin.register(Logactividad)
class LogactividadAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'usuario_display', 'accion', 'detalles')
    list_filter = ('accion', 'fecha')
    search_fields = ('usuario__user__username', 'detalles')

    def usuario_display(self, obj):
        return obj.usuario.user.username if obj.usuario and obj.usuario.user else 'N/A'
    usuario_display.short_description = 'Usuario'