from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class Client(TenantMixin):
    nombre_empresa = models.CharField(max_length=100)
    email_contacto = models.EmailField()
    fecha_creacion = models.DateField(auto_now_add=True)

    PLANES_CHOICES = (
        ('basico', 'Plan Emprendedor - $20'),
        ('pro', 'Plan Empresarial - $50'),
    )
    plan = models.CharField(max_length=20, choices=PLANES_CHOICES, default='basico')
    esta_activo = models.BooleanField(default=True)

    auto_create_schema = True
    auto_drop_schema = True 

    def __str__(self):
        return self.nombre_empresa

class Domain(DomainMixin):
    pass