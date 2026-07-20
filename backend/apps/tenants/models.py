from django.db import models
from django.utils import timezone
from django_tenants.models import TenantMixin, DomainMixin
from django.conf import settings

class Plan(models.Model):
    """
    Define los diferentes planes de suscripción que un cliente puede contratar.
    """
    nombre = models.CharField(max_length=100, unique=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    limite_usuarios = models.PositiveIntegerField(default=1)
    limite_sucursales = models.PositiveIntegerField(default=1)
    descripcion = models.TextField(blank=True, default='')
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class Client(TenantMixin):
    """
    Modelo principal que representa a un inquilino (tenant) en el sistema.
    Cada 'Client' tiene su propio esquema de base de datos aislado.
    """
    TIPO_NEGOCIO_CHOICES = (
        ('retail', 'Retail (Venta al Detal)'),
        ('b2b', 'B2B (Mayorista/Fabricante)'),
    )
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nombre_empresa = models.CharField(max_length=100)
    email_contacto = models.EmailField()
    esta_activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # --- NUEVOS CAMPOS ---
    tipo_negocio = models.CharField(max_length=10, choices=TIPO_NEGOCIO_CHOICES, default='retail', help_text="Modelo de negocio principal del inquilino.")
    onboarding_completado = models.BooleanField(default=False, help_text="Indica si el inquilino ha completado el asistente de configuración inicial.")

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
    estado = models.CharField(max_length=20, default='active') # active, expired, cancelled

    @property
    def is_active(self):
        """Propiedad que determina si la suscripción está actualmente activa."""
        return self.estado == 'active' and self.fecha_fin >= timezone.now().date()