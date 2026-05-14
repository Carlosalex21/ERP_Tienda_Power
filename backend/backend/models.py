from django.db import models
from apps.facturacion.models import Factura # Asumiendo que Factura está en apps.facturacion

class MetodoPagoConfig(models.Model):
    """
    Configuración general de un método de pago para el tenant.
    """
    nombre = models.CharField(max_length=100, unique=True, help_text="Ej: Pago Móvil, Zelle, Efectivo")
    activo = models.BooleanField(default=True)
    es_manual = models.BooleanField(default=False, help_text="Indica si el pago requiere verificación manual.")
    instrucciones = models.TextField(blank=True, null=True, help_text="Instrucciones para el cliente (ej: datos de Pago Móvil).")

    class Meta:
        verbose_name = "Configuración de Método de Pago"
        verbose_name_plural = "Configuraciones de Métodos de Pago"

    def __str__(self):
        return self.nombre

class PagoMovilConfig(models.Model):
    """
    Configuración específica para Pago Móvil por tenant.
    """
    metodo_pago = models.OneToOneField(MetodoPagoConfig, on_delete=models.CASCADE, related_name='pago_movil_config')
    banco = models.CharField(max_length=100)
    cedula = models.CharField(max_length=20)
    telefono = models.CharField(max_length=20)

    class Meta:
        verbose_name = "Configuración Pago Móvil"
        verbose_name_plural = "Configuraciones Pago Móvil"

class ZelleConfig(models.Model):
    """
    Configuración específica para Zelle por tenant.
    """
    metodo_pago = models.OneToOneField(MetodoPagoConfig, on_delete=models.CASCADE, related_name='zelle_config')
    email_zelle = models.EmailField()
    nombre_beneficiario = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Configuración Zelle"
        verbose_name_plural = "Configuraciones Zelle"

class TransaccionPasarela(models.Model):
    """
    Registro de transacciones con pasarelas de pago externas.
    """
    factura = models.ForeignKey(Factura, on_delete=models.SET_NULL, null=True, blank=True)
    metodo_pago = models.ForeignKey(MetodoPagoConfig, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    referencia_externa = models.CharField(max_length=255, blank=True, null=True, help_text="ID de transacción de la pasarela.")
    estado = models.CharField(max_length=50, default="pendiente", help_text="Ej: pendiente, completado, fallido, reembolsado.")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Transacción de Pasarela"
        verbose_name_plural = "Transacciones de Pasarela"