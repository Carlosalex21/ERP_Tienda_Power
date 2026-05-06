from django.db import models

class Cliente(models.Model): #listo
    tipo_documento = models.CharField(max_length=10)
    documento = models.CharField(max_length=20)
    nombre = models.CharField(max_length=100)
    email = models.CharField(unique=True, max_length=254)
    telefono = models.CharField(max_length=15, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    codigo_postal = models.CharField(max_length=5, blank=True, null=True)
    provincia = models.CharField(max_length=50, blank=True, null=True)
    fecha_registro = models.DateTimeField(blank=True, null=True)
    usuario = models.ForeignKey('usuarios.UserMetadata', models.DO_NOTHING, blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Cliente'
        unique_together = (('tipo_documento', 'documento'),)

    def __str__(self):
        return self.nombre