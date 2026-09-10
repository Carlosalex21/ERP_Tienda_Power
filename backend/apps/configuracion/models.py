from django.db import models

class Configuracioniva(models.Model):
    nombre = models.CharField(max_length=20, blank=True, null=True, verbose_name="Nombre del IVA", help_text="Ej: IVA General, IVA Reducido")
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Porcentaje (%)")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        db_table = 'ConfiguracionIVA'
        verbose_name = "Configuración de IVA"
        verbose_name_plural = "Configuraciones de IVA"

class Tipodocumentofiscal(models.Model):
    codigo = models.CharField(unique=True, max_length=10, verbose_name="Código")
    descripcion = models.CharField(max_length=100, verbose_name="Descripción")
    obligatorio = models.BooleanField(default=False, verbose_name="Obligatorio")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        db_table = 'TipoDocumentoFiscal'
        verbose_name = "Tipo de Documento Fiscal"
        verbose_name_plural = "Tipos de Documentos Fiscales"

class ConfiguracionCorrelativo(models.Model):
    prefijo = models.CharField(max_length=10, default="F-", verbose_name="Prefijo", help_text="Prefijo para el número de factura (ej: F-).")
    current_number = models.IntegerField(default=0, verbose_name="Número Actual", help_text="El último número de factura utilizado.")
    number_length = models.IntegerField(default=3, verbose_name="Longitud del Número", help_text="Número de dígitos para el correlativo (ej: 3 para 001).")
    # --- Número de Control SENIAT ---
    prefijo_numero_control = models.CharField(
        max_length=10, default="CTRL-", verbose_name="Prefijo Número de Control",
        help_text="Prefijo para el número de control SENIAT (ej: CTRL-, NC-)."
    )
    current_control_number = models.IntegerField(
        default=0, verbose_name="Número de Control Actual",
        help_text="El último número de control utilizado."
    )
    control_number_length = models.IntegerField(
        default=5, verbose_name="Longitud del Número de Control",
        help_text="Número de dígitos para el control (ej: 5 para 00001)."
    )

    class Meta:
        db_table = 'ConfiguracionCorrelativo'
        verbose_name = "Configuración de Correlativo"
        verbose_name_plural = "Configuraciones de Correlativos"



class ConfiguracionEmpresa(models.Model):
    """
    Almacena la configuración específica de la empresa para cada tenant.
    Se asume que solo habrá una instancia de este modelo por tenant (con pk=1).
    """
    nombre_comercial = models.CharField(max_length=255, default="Mi Empresa", verbose_name="Nombre Comercial")
    razon_social = models.CharField(max_length=255, blank=True, null=True, verbose_name="Razón Social")
    rif = models.CharField(max_length=20, blank=True, null=True, verbose_name="RIF / ID Fiscal")
    telefono = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono de la Empresa", help_text="Número para recibir notificaciones de pedidos.")
    direccion = models.TextField(blank=True, null=True, verbose_name="Dirección Fiscal")
    logo = models.ImageField(upload_to='logos_empresas/', null=True, blank=True, verbose_name="Logo de la Empresa")

    class Meta:
        verbose_name = "Configuración de la Empresa"
        verbose_name_plural = "Configuración de la Empresa"

    def __str__(self):
        return f"Configuración de {self.nombre_comercial}"


class Moneda(models.Model):
    """
    Representa una moneda utilizada por el tenant.

    Permite facturar y operar en múltiples divisas de forma simultánea.
    La moneda con ``es_predeterminada=True`` es la base (funcional) del tenant.
    """
    codigo = models.CharField(max_length=3, unique=True, verbose_name="Código ISO 4217")
    nombre = models.CharField(max_length=50, verbose_name="Nombre")
    simbolo = models.CharField(max_length=5, blank=True, null=True, verbose_name="Símbolo")
    es_predeterminada = models.BooleanField(default=False, verbose_name="Es moneda base")
    activa = models.BooleanField(default=True, verbose_name="Activa")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        db_table = 'Moneda'
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"
        ordering = ['-es_predeterminada', 'codigo']

    def __str__(self) -> str:
        return f"{self.nombre} ({self.codigo})"


class TasaCambio(models.Model):
    """
    Historial de tasas de cambio de una moneda frente a la moneda base
    (predeterminada) del tenant.

    Cada registro representa la tasa vigente en un momento concreto, lo que
    permite convertisiones históricas y revalorizaciones.
    """
    moneda = models.ForeignKey(
        Moneda,
        on_delete=models.CASCADE,
        related_name="tasas_cambio",
        verbose_name="Moneda",
    )
    fecha = models.DateField(auto_now_add=True, verbose_name="Fecha")
    tasa = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        verbose_name="Tasa",
        help_text="Tasa: 1 unidad de la moneda = tasa unidades de la moneda base.",
    )
    fuente = models.CharField(max_length=100, blank=True, null=True, verbose_name="Fuente")
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        db_table = 'TasaCambio'
        verbose_name = "Tasa de Cambio"
        verbose_name_plural = "Tasas de Cambio"
        ordering = ['-fecha', '-id']
        indexes = [
            models.Index(fields=['moneda', 'fecha'], name='idx_moneda_fecha'),
        ]

    def __str__(self) -> str:
        return f"{self.moneda.codigo}: {self.tasa} ({self.fecha})"
