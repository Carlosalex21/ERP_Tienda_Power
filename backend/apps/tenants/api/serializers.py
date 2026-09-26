from datetime import date

from rest_framework import serializers
from django.contrib.auth.models import User
from ..models import Plan, Subscription, Client, Domain, PlatformPaymentConfig, SubscriptionPayment, PlatformSettings

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
        fields = ('id', 'nombre', 'slug', 'precio', 'limite_usuarios', 'limite_sucursales', 'limite_productos')

class SubscriptionForClientSerializer(serializers.ModelSerializer):
    plan = PlanForClientSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    # El plan de prueba también queda `is_active=True` -- sin esto, /pago no
    # podía distinguir "ya pagó un plan real" de "está en su prueba
    # gratuita" y ocultaba las opciones de pago apenas alguien se registraba.
    es_prueba = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ('plan', 'estado', 'fecha_fin', 'is_active', 'es_prueba')

    def get_es_prueba(self, obj) -> bool:
        return bool(obj.plan and obj.plan.nombre == 'Plan de Prueba')

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
        choices=[
            ('retail', 'Retail'),
            ('b2b', 'B2B'),
            ('restaurante', 'Restaurante / Bar'),
            ('farmacia', 'Farmacia'),
            ('servicios', 'Taller / Servicios'),
            ('contador', 'Contador / Firma Contable'),
        ],
        required=True,
        help_text="Define el modelo de negocio principal del tenant.",
    )
    pais_codigo = serializers.ChoiceField(
        choices=[('VE', 'Venezuela'), ('CO', 'Colombia'), ('PE', 'Perú')],
        required=True,
        help_text=(
            "País de operación, elegido como primer paso del registro. "
            "Condiciona la moneda base y las tasas de IVA/IGV que se siembran para el tenant."
        ),
    )
    plan_id = serializers.IntegerField(required=False, help_text="Opcional. ID del plan a contratar. Si no se provee, se asigna un plan de prueba.")
    codigo_referido = serializers.CharField(
        required=False, allow_blank=True, max_length=50,
        help_text="Opcional. Subdominio del tenant que invitó a este registro (ver programa de referidos).",
    )
    cantidad_mesas = serializers.IntegerField(
        required=False,
        default=6,
        min_value=1,
        max_value=200,
        help_text="Solo aplica si tipo_negocio='restaurante': cantidad de mesas a sembrar (el dueño puede agregar/quitar después desde el panel).",
    )

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

class TenantSubscriptionStatusSerializer(serializers.Serializer):
    """
    Estado de suscripción del tenant actual, para que el frontend muestre un
    badge ("Prueba gratis: 5 días", "Plan Pro", "Suscripción vencida") y
    sepa cuándo redirigir a pagar.
    """
    plan_id = serializers.IntegerField(allow_null=True)
    plan_nombre = serializers.CharField(allow_null=True)
    plan_slug = serializers.CharField(allow_null=True)
    plan_precio = serializers.CharField(allow_null=True)
    estado = serializers.CharField(allow_null=True)
    fecha_fin = serializers.DateField(allow_null=True)
    is_active = serializers.BooleanField()
    dias_restantes = serializers.IntegerField(allow_null=True)
    es_prueba = serializers.BooleanField()

    @staticmethod
    def from_subscription(sub):
        if sub is None:
            return {
                'plan_id': None, 'plan_nombre': None, 'plan_slug': None, 'plan_precio': None,
                'estado': None, 'fecha_fin': None,
                'is_active': False, 'dias_restantes': None, 'es_prueba': False,
            }
        # `date.today()`, no `timezone.now().date()` -- mismo motivo que
        # `Subscription.is_active` (ver apps.tenants.models): `fecha_fin` se
        # graba con la fecha del SO, no con la de `TIME_ZONE`.
        dias_restantes = (sub.fecha_fin - date.today()).days if sub.fecha_fin else None
        return {
            'plan_id': sub.plan.id if sub.plan else None,
            'plan_nombre': sub.plan.nombre if sub.plan else None,
            'plan_slug': sub.plan.slug if sub.plan else None,
            'plan_precio': str(sub.plan.precio) if sub.plan else None,
            'estado': sub.estado,
            'fecha_fin': sub.fecha_fin,
            'is_active': sub.is_active,
            'dias_restantes': dias_restantes,
            'es_prueba': bool(sub.plan and sub.plan.nombre == 'Plan de Prueba'),
        }


class TenantProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para exponer la información del tenant actual al frontend.
    """
    subscription_status = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = (
            'nombre_empresa',
            'tipo_negocio',
            'onboarding_completado',
            'schema_name',
            'pais_codigo',
            'subscription_status',
        )

    def get_subscription_status(self, obj):
        sub = getattr(obj, 'subscription', None)
        return TenantSubscriptionStatusSerializer.from_subscription(sub)


class ReferidoItemSerializer(serializers.Serializer):
    """Un tenant que este dueño invitó -- solo lo mínimo, nunca datos internos del referido."""
    nombre_empresa = serializers.CharField()
    fecha_registro = serializers.DateTimeField()
    estado = serializers.CharField()

    def to_representation(self, instance):
        return {
            'nombre_empresa': instance.referido.nombre_empresa,
            'fecha_registro': instance.fecha_registro,
            'estado': instance.estado,
        }


class ReferidoProgramaSerializer(serializers.Serializer):
    """Resumen del programa de referidos para el dueño del tenant actual -- ver `ReferidoProgramaView`."""
    codigo_referido = serializers.CharField()
    link_invitacion = serializers.CharField()
    total_referidos = serializers.IntegerField()
    referidos_pendientes = serializers.IntegerField()
    referidos_recompensados = serializers.IntegerField()
    meses_ganados = serializers.IntegerField()
    referidos = ReferidoItemSerializer(many=True)


class TenantOnboardingUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer de escritura para `TenantProfileView` (PATCH). Expone
    únicamente `onboarding_completado` -- el resto de campos del perfil
    (país, tipo de negocio, schema_name) no deben poder cambiarse desde este
    endpoint genérico, así que ni siquiera se listan aquí.
    """

    class Meta:
        model = Client
        fields = ('onboarding_completado',)


class PlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = ('limite_registros_gratis', 'dias_gracia_tras_vencimiento')


class RegistrationQuotaSerializer(serializers.Serializer):
    cupos_restantes = serializers.IntegerField(allow_null=True)
    cupo_total = serializers.IntegerField(allow_null=True)


# --- SERIALIZERS PARA EL COBRO DE SUSCRIPCIONES SAAS (tenant -> plataforma) ---

class MiClienteSerializer(serializers.ModelSerializer):
    """
    Datos del `Client` del usuario autenticado, para que el flujo de pago de
    suscripción sepa a quién cobrarle y con qué método (según `pais_codigo`).
    """
    subscription = SubscriptionForClientSerializer(read_only=True)

    class Meta:
        model = Client
        fields = ('id', 'nombre_empresa', 'schema_name', 'pais_codigo', 'tipo_negocio', 'subscription')


class PlatformPaymentInfoSerializer(serializers.ModelSerializer):
    """
    Datos de cobro de la plataforma expuestos PÚBLICAMENTE (nunca las claves
    secretas): a dónde debe pagar Pago Móvil/Zelle un tenant venezolano, y la
    publishable key de Stripe para el resto de países.
    """
    class Meta:
        model = PlatformPaymentConfig
        fields = (
            'pago_movil_banco', 'pago_movil_cedula', 'pago_movil_telefono',
            'zelle_email', 'zelle_titular',
            'stripe_publishable_key',
        )


class PlatformPaymentConfigSerializer(serializers.ModelSerializer):
    """Serializer completo (con secretos, write_only) para el superadmin."""
    tiene_stripe_secret_key = serializers.SerializerMethodField()

    class Meta:
        model = PlatformPaymentConfig
        fields = (
            'pago_movil_banco', 'pago_movil_cedula', 'pago_movil_telefono',
            'zelle_email', 'zelle_titular',
            'stripe_publishable_key', 'stripe_secret_key', 'stripe_webhook_secret',
            'tiene_stripe_secret_key',
        )
        extra_kwargs = {
            'stripe_secret_key': {'write_only': True},
            'stripe_webhook_secret': {'write_only': True},
        }

    def get_tiene_stripe_secret_key(self, obj) -> bool:
        return bool(obj.stripe_secret_key)


class CrearPagoSuscripcionSerializer(serializers.Serializer):
    client_id = serializers.IntegerField(required=True)
    plan_id = serializers.IntegerField(required=True)
    metodo = serializers.ChoiceField(choices=SubscriptionPayment.METODO_CHOICES, required=True)
    periodo = serializers.ChoiceField(choices=SubscriptionPayment.PERIODO_CHOICES, required=False, default='mensual')
    referencia = serializers.CharField(required=False, allow_blank=True, default='')


class CrearPagoSuscripcionTenantSerializer(serializers.Serializer):
    """
    Igual que `CrearPagoSuscripcionSerializer` pero sin `client_id`: se llama
    DESDE el propio panel del tenant (autenticado como empleado/admin del
    tenant, no como el dueño en el esquema público), así que el cliente a
    cobrar es siempre `request.tenant` -- no hace falta ni conviene que el
    payload lo especifique.
    """
    plan_id = serializers.IntegerField(required=True)
    metodo = serializers.ChoiceField(choices=SubscriptionPayment.METODO_CHOICES, required=True)
    periodo = serializers.ChoiceField(choices=SubscriptionPayment.PERIODO_CHOICES, required=False, default='mensual')
    referencia = serializers.CharField(required=False, allow_blank=True, default='')


class PeriodoSuscripcionSerializer(serializers.Serializer):
    """Expone la config de períodos (`PERIODOS_SUSCRIPCION`) para que el frontend
    calcule y muestre los mismos montos/descuentos que realmente cobra el backend."""
    codigo = serializers.CharField()
    nombre = serializers.CharField()
    meses = serializers.IntegerField()
    dias = serializers.IntegerField()
    descuento_pct = serializers.IntegerField()


class SubscriptionPaymentClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ('id', 'nombre_empresa', 'schema_name', 'pais_codigo')


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    client = SubscriptionPaymentClienteSerializer(read_only=True)
    plan = PlanForClientSerializer(read_only=True)
    confirmado_por_username = serializers.CharField(source='confirmado_por.username', read_only=True, default=None)

    class Meta:
        model = SubscriptionPayment
        fields = (
            'id', 'client', 'plan', 'periodo', 'monto', 'metodo', 'referencia', 'estado',
            'fecha_creacion', 'fecha_confirmacion', 'confirmado_por_username', 'notas',
        )