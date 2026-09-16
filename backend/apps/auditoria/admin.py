from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'usuario_nombre', 'accion', 'modelo', 'objeto_repr')
    list_filter = ('accion', 'modelo')
    search_fields = ('objeto_repr', 'usuario_nombre', 'objeto_id')
    date_hierarchy = 'fecha'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
