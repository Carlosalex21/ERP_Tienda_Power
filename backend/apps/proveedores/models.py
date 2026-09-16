from django.db import models

class Proveedor(models.Model):
    identificador_fiscal = models.CharField(unique=True, max_length=10)
    nombre = models.CharField(max_length=100)
    direccion = models.TextField()
    telefono = models.CharField(max_length=15, blank=True, null=True)
    email = models.CharField(max_length=254)
    plazo_pago = models.IntegerField(blank=True, null=True)
    es_contribuyente_especial = models.BooleanField(
        default=False,
        help_text="Contribuyente Especial designado por el SENIAT -- aplica un porcentaje de retención de IVA distinto al de un contribuyente ordinario.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Proveedor'

    def __str__(self) -> str:
        return self.nombre