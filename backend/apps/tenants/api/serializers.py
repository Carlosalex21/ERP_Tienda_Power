from rest_framework import serializers
from apps.tenants.models import Plan, Subscription

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ('id', 'nombre', 'descripcion', 'precio', 'limite_usuarios', 'limite_sucursales')

class SubscriptionCreateSerializer(serializers.Serializer):
    client_id = serializers.IntegerField()
    plan_id = serializers.IntegerField()

class SubscriptionResponseSerializer(serializers.ModelSerializer):
    message = serializers.CharField(default="Suscripción creada/actualizada exitosamente")

    class Meta:
        model = Subscription
        fields = ('message', 'estado', 'fecha_fin')