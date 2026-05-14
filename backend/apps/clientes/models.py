from django.db import models
from django.utils import timezone

class Cliente(models.Model): #listo
    nombre = models.CharField(max_length=255, verbose_name="Nombre Completo", help_text="Nombre o razón social del cliente.")
    email = models.EmailField(blank=True, null=True, verbose_name="Correo Electrónico")
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono de Contacto")
    direccion = models.TextField(blank=True, null=True, verbose_name="Dirección Física")
    tipo_documento = models.CharField(
        max_length=50, blank=True, null=True, 
        verbose_name="Tipo de Documento", 
        help_text="Ej: Cédula, RIF, Pasaporte"
    )
    codigo_postal = models.CharField(max_length=10, blank=True, null=True, verbose_name="Código Postal")
    provincia = models.CharField(max_length=50, blank=True, null=True, verbose_name="Provincia o Estado")
    documento = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Documento")
    fecha_registro = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Registro")
    usuario = models.ForeignKey('usuarios.UserMetadata', models.SET_NULL, blank=True, null=True, verbose_name="Usuario Asociado", help_text="Usuario que registró al cliente.")
    activo = models.BooleanField(default=True, verbose_name="Activo", help_text="Indica si el cliente está activo.")

    class Meta:
        db_table = 'Cliente'
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        return self.nombre