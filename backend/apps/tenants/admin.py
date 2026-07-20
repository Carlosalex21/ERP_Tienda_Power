from django.contrib import admin
from .models import Client, Domain, Plan, Subscription

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio', 'limite_usuarios', 'activo')

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('client', 'plan', 'estado', 'fecha_fin', 'is_active')
    list_filter = ('estado', 'plan')
    search_fields = ('client__nombre_empresa', 'plan__nombre')
    readonly_fields = ('fecha_inicio',)
    list_display_links = ('client', 'plan')

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nombre_empresa', 'schema_name', 'owner', 'esta_activo', 'fecha_creacion')
    search_fields = ('nombre_empresa', 'schema_name', 'owner__username')

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')