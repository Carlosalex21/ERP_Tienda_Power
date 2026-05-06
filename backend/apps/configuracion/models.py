from django.db import models, transaction

class Configuracioniva(models.Model):
    nombre = models.CharField(max_length=20, blank=True, null=True)
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ConfiguracionIVA'

class Tipodocumentofiscal(models.Model):
    codigo = models.CharField(unique=True, max_length=10)
    descripcion = models.CharField(max_length=100)
    obligatorio = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'TipoDocumentoFiscal'

class ConfiguracionCorrelativo(models.Model):
    prefijo = models.CharField(max_length=10, default="F-")
    current_number = models.IntegerField(default=0)
    number_length = models.IntegerField(default=3)

    class Meta:
        db_table = 'ConfiguracionCorrelativo'