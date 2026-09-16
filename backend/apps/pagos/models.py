from django.db import models
from apps.facturacion.models import Factura # Asumiendo que Factura está en apps.facturacion


class Banco(models.Model):
    """
    Entidad bancaria (Banesco, Mercantil, Banco de Venezuela...). Un método
    de pago no-efectivo (`facturacion.MetodoPago`) apunta a un banco fijo --
    así, al cuadrar caja al final del día/turno, el reporte de "Cobros"
    puede agrupar por banco y compararlo contra el estado de cuenta real de
    esa cuenta (ver `CajaSesion` en apps.facturacion).
    """
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Banco'
        verbose_name = "Banco"
        verbose_name_plural = "Bancos"
        ordering = ['nombre']

    def __str__(self) -> str:
        return self.nombre


class MetodoPagoConfig(models.Model):
    """
    Configuración general de un método de pago para el tenant.
    """
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre del Método", help_text="Ej: Pago Móvil, Zelle, Efectivo")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    es_manual = models.BooleanField(default=False, verbose_name="Verificación Manual", help_text="Indica si el pago requiere verificación manual.")
    instrucciones = models.TextField(blank=True, null=True, verbose_name="Instrucciones para el Cliente", help_text="Instrucciones para el cliente (ej: datos de Pago Móvil).")

    class Meta:
        verbose_name = "Configuración de Método de Pago"
        verbose_name_plural = "Configuraciones de Métodos de Pago"

    def __str__(self):
        return self.nombre

class PagoMovilConfig(models.Model):
    """
    Configuración específica para Pago Móvil por tenant.
    """
    metodo_pago = models.OneToOneField(MetodoPagoConfig, on_delete=models.CASCADE, related_name='pago_movil_config', verbose_name="Método de Pago Asociado")
    banco = models.CharField(max_length=100, verbose_name="Banco")
    cedula = models.CharField(max_length=20, verbose_name="Cédula / RIF")
    telefono = models.CharField(max_length=20, verbose_name="Teléfono")

    class Meta:
        verbose_name = "Configuración Pago Móvil"
        verbose_name_plural = "Configuraciones Pago Móvil"

class ZelleConfig(models.Model):
    """
    Configuración específica para Zelle por tenant.
    """
    metodo_pago = models.OneToOneField(MetodoPagoConfig, on_delete=models.CASCADE, related_name='zelle_config', verbose_name="Método de Pago Asociado")
    email_zelle = models.EmailField(verbose_name="Email de Zelle")
    nombre_beneficiario = models.CharField(max_length=255, verbose_name="Nombre del Beneficiario")

    class Meta:
        verbose_name = "Configuración Zelle"
        verbose_name_plural = "Configuraciones Zelle"

class StripeConfig(models.Model):
    """
    Configuración de Stripe del tenant, para cobrar en moneda extranjera
    (tarjetas internacionales) desde el catálogo público.

    Cada tenant conecta su PROPIA cuenta de Stripe (no hay Stripe Connect
    aquí -- eso implicaría OAuth y verificación KYC por tenant, mucho más
    trabajo del que un negocio pequeño necesita para empezar a cobrar).
    `secret_key` nunca se expone en un serializer de lectura: solo se usa
    server-side para crear la Checkout Session.
    """
    metodo_pago = models.OneToOneField(MetodoPagoConfig, on_delete=models.CASCADE, related_name='stripe_config', verbose_name="Método de Pago Asociado")
    publishable_key = models.CharField(max_length=255, verbose_name="Publishable Key", help_text="Empieza con pk_test_ o pk_live_.")
    secret_key = models.CharField(max_length=255, verbose_name="Secret Key", help_text="Empieza con sk_test_ o sk_live_. Nunca se muestra de vuelta una vez guardada.")
    webhook_secret = models.CharField(max_length=255, blank=True, null=True, verbose_name="Webhook Signing Secret", help_text="whsec_... -- para que Stripe confirme pagos automáticamente.")
    moneda = models.CharField(max_length=3, default='usd', verbose_name="Moneda", help_text="Código ISO 4217 en minúsculas (usd, eur, etc).")

    class Meta:
        verbose_name = "Configuración de Stripe"
        verbose_name_plural = "Configuraciones de Stripe"

    @property
    def modo_test(self) -> bool:
        return self.secret_key.startswith('sk_test_')


class TransaccionPasarela(models.Model):
    """
    Registro de transacciones con pasarelas de pago externas.
    """
    factura = models.ForeignKey(Factura, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Factura Asociada")
    metodo_pago = models.ForeignKey(MetodoPagoConfig, on_delete=models.PROTECT, verbose_name="Método de Pago")
    monto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto")
    referencia_externa = models.CharField(max_length=255, blank=True, null=True, verbose_name="Referencia Externa", help_text="ID de transacción de la pasarela.")
    estado = models.CharField(max_length=50, default="pendiente", verbose_name="Estado", help_text="Ej: pendiente, completado, fallido, reembolsado.")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    fecha_actualizacion = models.DateTimeField(auto_now=True, verbose_name="Última Actualización")

    class Meta:
        verbose_name = "Transacción de Pasarela"
        verbose_name_plural = "Transacciones de Pasarela"

    def __str__(self) -> str:
        return f"Transacción {self.referencia_externa or f'#{self.pk}'} ({self.estado}) - Factura #{self.factura_id or 's/factura'}"