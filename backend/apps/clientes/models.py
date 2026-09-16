import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

class Cliente(models.Model):
    """
    Modelo para clientes de tipo Retail (venta al detal).
    Este modelo ya existía y es usado por el flujo de ventas públicas.
    """
    TIPO_DOCUMENTO_CHOICES = (
        ('V', 'Cédula Venezolana'),
        ('E', 'Cédula Extranjero'),
        ('J', 'RIF Jurídico'),
        ('G', 'RIF Gubernamental'),
        ('P', 'Pasaporte'),
    )
    nombre = models.CharField(max_length=255)
    tipo_documento = models.CharField(max_length=1, choices=TIPO_DOCUMENTO_CHOICES, blank=True, null=True, help_text="Tipo de documento de identidad del cliente.")
    documento = models.CharField(max_length=20, blank=True, null=True, help_text="Número de documento de identidad del cliente.")
    telefono = models.CharField(max_length=20, unique=True, blank=True, null=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    direccion = models.TextField(blank=True, default='')
    fecha_registro = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        """
        Metadatos para el modelo Cliente.
        - `unique_together`: Asegura que no haya dos clientes con el mismo tipo y número de documento.
        """
        unique_together = ('tipo_documento', 'documento')
        
    def __str__(self):
        return self.nombre

# --- NUEVOS MODELOS PARA EL ECOSISTEMA B2B ---

class NivelPrecio(models.Model):
    """
    Representa una categoría de precios para clientes B2B, permitiendo aplicar
    descuentos globales. Ej: 'Gran Mayor', 'Mayorista', 'VIP'.
    """
    nombre = models.CharField(max_length=100, unique=True, help_text="Nombre único para el nivel de precio. Ej: Mayorista")
    porcentaje_descuento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Porcentaje de descuento global para este nivel (ej: 15.00 para 15%)"
    )
    monto_minimo_periodo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text=(
            "Monto mínimo comprado por un cliente en el período de evaluación "
            "(ver `pricing_tier_service.PERIODO_EVALUACION_MESES`) para calificar "
            "automáticamente a este nivel. 0 = nivel de entrada, sin mínimo."
        ),
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Nivel de Precio"
        verbose_name_plural = "Niveles de Precios"
        ordering = ['monto_minimo_periodo', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.porcentaje_descuento}%)"


class ClienteB2B(models.Model):
    """
    Representa a un cliente de negocio (comprador) dentro del ecosistema de
    un tenant B2B (fabricante/mayorista).
    """
    ESTADO_CHOICES = (
        ('pendiente', 'Pendiente de Activación'),
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('bloqueado', 'Bloqueado'),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='cliente_b2b', help_text="Usuario para iniciar sesión en el portal B2B. Nulo hasta la activación.")
    razon_social = models.CharField(max_length=255, help_text="Nombre legal o comercial de la empresa cliente.")
    rif = models.CharField(max_length=20, unique=True, help_text="Registro de Identificación Fiscal (o equivalente local).")
    email_contacto = models.EmailField(unique=True, help_text="Email principal para comunicaciones y para la invitación.")
    telefono_contacto = models.CharField(max_length=30, blank=True)
    direccion_fiscal = models.TextField(blank=True)
    nivel_precio = models.ForeignKey(NivelPrecio, on_delete=models.PROTECT, related_name='clientes_b2b', help_text="Categoría de precios asignada a este cliente.")
    limite_credito = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        help_text="Monto máximo de crédito otorgado. 0 = sin línea de crédito configurada (no se restringe el pedido).",
    )
    nivel_precio_actualizado_en = models.DateTimeField(
        blank=True, null=True,
        help_text="Última vez que el sistema subió automáticamente el nivel de precio por volumen de compra.",
    )
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='pendiente')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cliente B2B"
        verbose_name_plural = "Clientes B2B"
        ordering = ['razon_social']

    def __str__(self):
        return f"{self.razon_social} ({self.rif})"


def default_expiration():
    """Devuelve la fecha y hora actual más 7 días."""
    return timezone.now() + timezone.timedelta(days=7)

class InvitacionB2B(models.Model):
    """
    Almacena el token único para que un ClienteB2B pueda activar su cuenta y
    crear su usuario a través de un enlace de invitación.
    """
    cliente_b2b = models.OneToOneField(ClienteB2B, on_delete=models.CASCADE, related_name='invitacion')
    email = models.EmailField(help_text="Email al que se envió la invitación. Se mantiene por referencia.")
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    fecha_expiracion = models.DateTimeField(default=default_expiration)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    utilizada = models.BooleanField(default=False)

    def is_expired(self):
        """Verifica si la invitación ha expirado."""
        return timezone.now() > self.fecha_expiracion

    def __str__(self):
        return f"Invitación para {self.email}"