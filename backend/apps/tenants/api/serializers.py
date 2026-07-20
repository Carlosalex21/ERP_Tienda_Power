from rest_framework import serializers
from django.contrib.auth.models import User
from ..models import Plan, Subscription, Client, Domain

# --- Serializers existentes (inferidos de tus vistas) ---

class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = '__all__'

class SubscriptionCreateSerializer(serializers.Serializer):
    client_id = serializers.IntegerField(required=True)
    plan_id = serializers.IntegerField(required=True)

class SubscriptionResponseSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    class Meta:
        model = Subscription
        fields = '__all__'

# --- NUEVOS SERIALIZERS PARA LA VISTA DE ADMINISTRADOR ---

class DomainForClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ('domain', 'is_primary')

class PlanForClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ('nombre',)

class SubscriptionForClientSerializer(serializers.ModelSerializer):
    plan = PlanForClientSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    class Meta:
        model = Subscription
        fields = ('plan', 'estado', 'fecha_fin', 'is_active') # is_active es un método en el modelo

class OwnerForClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email')

class PlatformClientSerializer(serializers.ModelSerializer):
    """
    Serializer detallado para la vista de lista de clientes del administrador.
    """
    owner = OwnerForClientSerializer(read_only=True)
    subscription = SubscriptionForClientSerializer(read_only=True)
    domains = DomainForClientSerializer(many=True, read_only=True)

    class Meta:
        model = Client
        fields = (
            'id', 
            'nombre_empresa', 
            'schema_name', 
            'owner', 
            'subscription', 
            'domains', 
            'esta_activo', 
            'fecha_creacion'
        )

# SERIALIZERS PARA EL REGISTRO DE TENANTS

class TenantRegistrationSerializer(serializers.Serializer):
    """
    Serializer para registrar un nuevo usuario y crear su tenant.
    """
    first_name = serializers.CharField(required=True, max_length=150, help_text="Nombre de la persona que se registra.")
    last_name = serializers.CharField(required=True, max_length=150, help_text="Apellido de la persona que se registra.")
    username = serializers.RegexField(
        regex=r'^[\w.@+-]+$',
        required=True,
        max_length=150,
        help_text="Usuario para iniciar sesión. Solo letras, números y @/./+/-/_."
    )
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    nombre_empresa = serializers.CharField(required=True, max_length=100)
    subdomain = serializers.RegexField(
        regex=r'^[a-z0-9]+(?:-[a-z0-9]+)*$',
        required=True,
        max_length=50,
        help_text="Solo letras minúsculas, números y guiones. Ej: 'mi-tienda'"
    )
    tipo_negocio = serializers.ChoiceField(
        choices=[('retail', 'Retail'), ('b2b', 'B2B')],
        required=True,
        help_text="Define el modelo de negocio principal del tenant."
    )
    plan_id = serializers.IntegerField(required=False, help_text="Opcional. ID del plan a contratar. Si no se provee, se asigna un plan de prueba.")

    def validate_subdomain(self, value):
        """Verifica que el subdominio no sea una palabra reservada."""
        if value in ['www', 'api', 'admin', 'mail', 'app', 'public']:
            raise serializers.ValidationError("Este subdominio está reservado.")
        return value

    def validate_username(self, value):
        """Verifica que el nombre de usuario no esté ya en uso en el esquema público."""
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Este nombre de usuario ya está en uso.")
        return value

    def validate_email(self, value):
        """Verifica que el email no esté ya en uso en el esquema público."""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Este correo electrónico ya está registrado.")
        return value

# --- NUEVOS SERIALIZERS PARA EL DASHBOARD DE PLATAFORMA ---

class DashboardBusinessMetricsSerializer(serializers.Serializer):
    active_tenants = serializers.IntegerField()
    active_subscriptions = serializers.IntegerField()
    monthly_recurring_revenue = serializers.CharField()
    new_clients_last_30_days = serializers.IntegerField()

class DashboardSystemHealthSerializer(serializers.Serializer):
    cpu_usage_percent = serializers.FloatField(allow_null=True)
    memory_usage_percent = serializers.FloatField(allow_null=True)
    disk_usage_percent = serializers.FloatField(allow_null=True)

class DashboardDbHealthSerializer(serializers.Serializer):
    active_connections = serializers.IntegerField()
    max_connections = serializers.IntegerField()
    usage_percent = serializers.FloatField()

class PlatformDashboardSerializer(serializers.Serializer):
    business_metrics = DashboardBusinessMetricsSerializer()
    system_health = DashboardSystemHealthSerializer()
    db_health = DashboardDbHealthSerializer()

class TenantProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para exponer la información del tenant actual al frontend.
    """
    class Meta:
        model = Client
        fields = (
            'nombre_empresa',
            'tipo_negocio',
            'onboarding_completado',
            'schema_name',
        )