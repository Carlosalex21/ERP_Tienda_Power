from django.contrib import admin
from .models import Client, Domain, Plan, Subscription

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio', 'limite_usuarios', 'activo')

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'plan', 'estado', 'fecha_fin')
    list_filter = ('estado', 'plan')

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nombre_empresa', 'schema_name', 'esta_activo', 'fecha_creacion')

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')