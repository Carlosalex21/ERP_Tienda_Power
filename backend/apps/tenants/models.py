from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
from django.utils import timezone

class Plan(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stripe_price_id = models.CharField(max_length=100, blank=True, null=True)
    limite_usuarios = models.IntegerField(default=1)
    limite_sucursales = models.IntegerField(default=1)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} - ${self.precio}"

class Subscription(models.Model):
    ESTADOS_CHOICES = (
        ('activa', 'Activa'),
        ('expirada', 'Expirada'),
        ('cancelada', 'Cancelada'),
        ('pendiente', 'Pendiente de Pago'),
    )
    cliente = models.OneToOneField('Client', on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.RESTRICT)
    estado = models.CharField(max_length=20, choices=ESTADOS_CHOICES, default='pendiente')
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_fin = models.DateTimeField(blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)

    def is_active(self):
        if self.estado == 'activa' and (not self.fecha_fin or self.fecha_fin > timezone.now()):
            return True
        return False

    def __str__(self):
        return f"Suscripción de {self.cliente.nombre_empresa} - {self.plan.nombre}"

class Client(TenantMixin):
    nombre_empresa = models.CharField(max_length=100)
    email_contacto = models.EmailField()
    fecha_creacion = models.DateField(auto_now_add=True)

    # El plan antiguo se reemplaza por el modelo Subscription relacionado,
    # pero mantenemos esta_activo que usaremos como flag secundario o general.
    esta_activo = models.BooleanField(default=True)

    auto_create_schema = True
    auto_drop_schema = True 

    def __str__(self):
        return self.nombre_empresa

    @property
    def has_active_subscription(self):
        if hasattr(self, 'subscription'):
            return self.subscription.is_active()
        return False

class Domain(DomainMixin):
    pass