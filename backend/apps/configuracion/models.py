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