from datetime import date

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
from django.conf import settings


class PlatformSettings(models.Model):
    """
    Configuración global de la plataforma (fila única, pk=1). Separada de
    `PlatformPaymentConfig` (que son credenciales de cobro): esto son
    parámetros de negocio -- cupo de registros gratuitos y período de
    gracia tras vencer una suscripción.
    """
    limite_registros_gratis = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Máximo de tenants que pueden registrarse en total (todos arrancan en el plan de prueba). Vacío = sin límite.",
    )
    dias_gracia_tras_vencimiento = models.PositiveIntegerField(
        default=3,
        help_text="Días tras vencer la suscripción antes de bloquear el acceso al panel del tenant.",
    )

    class Meta:
        verbose_name = "Configuración de la Plataforma"
        verbose_name_plural = "Configuración de la Plataforma"

    def __str__(self):
        return "Configuración de la plataforma"


class Plan(models.Model):
    """
    Define los diferentes planes de suscripción que un cliente puede contratar.
    """
    nombre = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=50, unique=True, null=True, blank=True, help_text="Identificador estable usado por el frontend (ej: 'emprendedor', 'pro'). No cambia aunque se edite el nombre visible.")
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    limite_usuarios = models.PositiveIntegerField(default=1)
    limite_sucursales = models.PositiveIntegerField(default=1)
    limite_productos = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Máximo de productos activos que puede tener el tenant. Vacío = sin límite.",
    )
    descripcion = models.TextField(blank=True, default='')
    activo = models.BooleanField(default=True)
    # A qué tipos de negocio se le ofrece/cobra este plan (ver
    # Client.TIPO_NEGOCIO_CHOICES) -- un contador no necesita lo mismo que
    # una tienda al detal, y no tiene sentido cobrarles igual. Vacío =
    # aplica a todos (así los planes ya existentes, sembrados antes de este
    # campo, siguen mostrándose a cualquiera sin tener que migrarlos a mano).
    tipos_negocio = ArrayField(
        models.CharField(max_length=20),
        blank=True,
        default=list,
        help_text="Tipos de negocio a los que aplica este plan. Vacío = aplica a todos.",
    )

    def __str__(self):
        return self.nombre

class Client(TenantMixin):
    """
    Modelo principal que representa a un inquilino (tenant) en el sistema.
    Cada 'Client' tiene su propio esquema de base de datos aislado.
    """
    # Cada tipo habilita/oculta módulos propios en el panel (ver
    # `modulosPanel.ts` en el frontend y `Sidebar.tsx`) -- un tenant tiene
    # UN tipo principal, no una combinación; si en el futuro un negocio
    # necesita mezclar verticales (ej. una farmacia con restaurante adentro)
    # se resuelve activando módulos individuales, no agregando un choice
    # nuevo por cada combinación posible.
    TIPO_NEGOCIO_CHOICES = (
        ('retail', 'Retail (Venta al Detal)'),
        ('b2b', 'B2B (Mayorista/Fabricante)'),
        ('restaurante', 'Restaurante / Bar'),
        ('farmacia', 'Farmacia'),
        ('servicios', 'Taller / Servicios'),
        ('contador', 'Contador / Firma Contable'),
    )
    # Países soportados por el motor fiscal (ver apps.configuracion.core.tax_strategy).
    # Se duplica aquí como constante simple en vez de importar el registro de
    # estrategias: este modelo vive en el esquema público (SHARED_APPS) y no
    # debe acoplarse a un módulo de las TENANT_APPS.
    PAIS_CHOICES = (
        ('VE', 'Venezuela'),
        ('CO', 'Colombia'),
        ('PE', 'Perú'),
    )
    # PROTECT (no CASCADE): ``auth.User`` es una TENANT_APP -- cada esquema
    # tiene su propia tabla ``auth_user`` con IDs propios que empiezan en 1,
    # así que un ID de usuario puede coincidir por pura casualidad entre
    # esquemas distintos. Con CASCADE, borrar un usuario cualquiera en
    # CUALQUIER tenant podía terminar borrando -- en cascada y en silencio --
    # un ``Client`` (tenant) completamente distinto cuyo ``owner_id``
    # coincidiera numéricamente. PROTECT convierte ese borrado accidental en
    # un error explícito en vez de destruir datos de otro tenant.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    nombre_empresa = models.CharField(max_length=100)
    email_contacto = models.EmailField()
    esta_activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # --- NUEVOS CAMPOS ---
    tipo_negocio = models.CharField(max_length=20, choices=TIPO_NEGOCIO_CHOICES, default='retail', help_text="Modelo de negocio principal del inquilino.")
    onboarding_completado = models.BooleanField(default=False, help_text="Indica si el inquilino ha completado el asistente de configuración inicial.")
    pais_codigo = models.CharField(
        max_length=2, choices=PAIS_CHOICES, default='VE',
        help_text="País de operación del inquilino. Determina moneda base, IVA e impuestos aplicables desde el alta.",
    )

    auto_create_schema = True
    auto_drop_schema = True

    def __str__(self):
        return self.nombre_empresa

class Domain(DomainMixin):
    pass

class Subscription(models.Model):
    client = models.OneToOneField(Client, on_delete=models.CASCADE, null=True, blank=True)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    fecha_inicio = models.DateField(auto_now_add=True)
    fecha_fin = models.DateField(blank=True, null=True)
    # Nota: en español para que coincida con SubscriptionService, el dashboard
    # de plataforma y las migraciones existentes ('activa'/'expirada'/
    # 'cancelada'/'pendiente') -- antes decía 'active' en inglés aquí y esta
    # propiedad nunca era True para ninguna suscripción creada por el código real.
    estado = models.CharField(max_length=20, default='pendiente')

    @property
    def is_active(self):
        """Propiedad que determina si la suscripción está actualmente activa."""
        # `date.today()` (no `timezone.now().date()`) a propósito: `fecha_fin`
        # es un `DateField` que se graba con la fecha del SO (ver la nota en
        # `apps.tenants.services.subscription_service`); usar
        # `timezone.now().date()` puede adelantarse un día y cortarle el
        # acceso a un tenant que en realidad todavía tiene suscripción vigente.
        return self.estado == 'activa' and self.fecha_fin is not None and self.fecha_fin >= date.today()


class PlatformPaymentConfig(models.Model):
    """
    Datos de cobro DEL DUEÑO DE LA PLATAFORMA (no de un tenant) para recibir
    el pago de las suscripciones SaaS. Fila única (pk=1), editable solo por
    el superadmin. Análogo a `apps.pagos.models.PagoMovilConfig/ZelleConfig/
    StripeConfig` pero a nivel de plataforma: aquí el dinero fluye del
    dueño del tenant hacia la plataforma, no de un cliente final hacia el tenant.
    """
    pago_movil_banco = models.CharField(max_length=100, blank=True, default='')
    pago_movil_cedula = models.CharField(max_length=20, blank=True, default='')
    pago_movil_telefono = models.CharField(max_length=20, blank=True, default='')
    zelle_email = models.EmailField(blank=True, default='')
    zelle_titular = models.CharField(max_length=255, blank=True, default='')
    stripe_publishable_key = models.CharField(max_length=255, blank=True, default='')
    stripe_secret_key = models.CharField(max_length=255, blank=True, default='')
    stripe_webhook_secret = models.CharField(max_length=255, blank=True, default='')
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de Cobro de la Plataforma"
        verbose_name_plural = "Configuración de Cobro de la Plataforma"

    def __str__(self):
        return "Configuración de cobro de la plataforma"

    @property
    def stripe_modo_test(self) -> bool:
        return self.stripe_secret_key.startswith('sk_test_')


class SubscriptionPayment(models.Model):
    """
    Registro de un intento/confirmación de pago de una suscripción SaaS
    (el tenant le paga a LA PLATAFORMA, no al revés). Para Venezuela el
    pago es manual (Pago Móvil/Zelle) y requiere confirmación humana desde
    el panel de superadmin; para el resto de países se paga con Stripe
    Checkout contra la cuenta de Stripe de la propia plataforma y se
    confirma automáticamente vía webhook.
    """
    METODO_CHOICES = (
        ('pago_movil', 'Pago Móvil'),
        ('zelle', 'Zelle'),
        ('stripe', 'Stripe'),
    )
    ESTADO_CHOICES = (
        ('pendiente', 'Pendiente de confirmación'),
        ('confirmado', 'Confirmado'),
        ('rechazado', 'Rechazado'),
    )
    PERIODO_CHOICES = (
        ('mensual', 'Mensual'),
        ('trimestral', 'Trimestral'),
        ('anual', 'Anual'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='pagos_suscripcion')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    periodo = models.CharField(max_length=20, choices=PERIODO_CHOICES, default='mensual')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODO_CHOICES)
    referencia = models.CharField(max_length=255, blank=True, default='', help_text="Número de referencia reportado por el cliente (Pago Móvil/Zelle).")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    stripe_session_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_confirmacion = models.DateTimeField(blank=True, null=True)
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    notas = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = "Pago de Suscripción"
        verbose_name_plural = "Pagos de Suscripción"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"{self.client.nombre_empresa} - {self.plan.nombre} ({self.estado})"