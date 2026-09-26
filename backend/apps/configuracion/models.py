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
    # El formato real que exige el SENIAT es "<código de sucursal/terminal de
    # 2 dígitos>-<correlativo>" (ej: "00-00000001"), no un prefijo de texto
    # libre como "CTRL-" (que no es un número de control válido ante el ente).
    prefijo_numero_control = models.CharField(
        max_length=10, default="00-", verbose_name="Prefijo Número de Control",
        help_text="Prefijo para el número de control SENIAT (ej: 00- para la sucursal única/matriz)."
    )
    current_control_number = models.IntegerField(
        default=0, verbose_name="Número de Control Actual",
        help_text="El último número de control utilizado."
    )
    control_number_length = models.IntegerField(
        default=8, verbose_name="Longitud del Número de Control",
        help_text="Número de dígitos para el control (ej: 8 para 00000001)."
    )

    # --- Número de Control para Notas de Crédito/Débito ---
    # Antes las notas usaban `current_control_number` -- el MISMO contador
    # que las facturas -- así que cada nota emitida "robaba" un número de la
    # secuencia de facturas. El SENIAT exige que cada tipo de documento
    # (factura, nota de crédito, nota de débito) lleve su propia numeración
    # de control correlativa e independiente.
    prefijo_numero_control_nota_credito = models.CharField(
        max_length=10, default="00-", verbose_name="Prefijo Número de Control (Nota de Crédito)",
    )
    current_control_number_nota_credito = models.IntegerField(
        default=0, verbose_name="Número de Control Actual (Nota de Crédito)",
    )
    control_number_length_nota_credito = models.IntegerField(
        default=8, verbose_name="Longitud del Número de Control (Nota de Crédito)",
    )
    prefijo_numero_control_nota_debito = models.CharField(
        max_length=10, default="00-", verbose_name="Prefijo Número de Control (Nota de Débito)",
    )
    current_control_number_nota_debito = models.IntegerField(
        default=0, verbose_name="Número de Control Actual (Nota de Débito)",
    )
    control_number_length_nota_debito = models.IntegerField(
        default=8, verbose_name="Longitud del Número de Control (Nota de Débito)",
    )

    # --- Correlativo de Nota de Entrega ---
    # Simple, no fiscal (una nota de entrega todavía no es un comprobante
    # fiscal -- ver `apps.facturacion.services.nota_entrega_service`, se
    # convierte en factura real recién al confirmarse el cobro/crédito). Sin
    # esto, una nota de entrega quedaba sin ningún número mientras estuviera
    # en ese estado -- imposible referenciarla al imprimirla o en el listado.
    prefijo_nota_entrega = models.CharField(
        max_length=10, default="NE-", verbose_name="Prefijo Nota de Entrega",
    )
    current_number_nota_entrega = models.IntegerField(
        default=0, verbose_name="Número Actual (Nota de Entrega)",
    )
    number_length_nota_entrega = models.IntegerField(
        default=3, verbose_name="Longitud del Número (Nota de Entrega)",
    )

    class Meta:
        db_table = 'ConfiguracionCorrelativo'
        verbose_name = "Configuración de Correlativo"
        verbose_name_plural = "Configuraciones de Correlativos"

    def __str__(self) -> str:
        return f"Numeración de facturas ({self.prefijo}{str(self.current_number).zfill(self.number_length)} emitido hasta ahora)"



class ConfiguracionEmpresa(models.Model):
    """
    Almacena la configuración específica de la empresa para cada tenant.
    Se asume que solo habrá una instancia de este modelo por tenant (con pk=1).
    """
    PAIS_CHOICES = (
        ('VE', 'Venezuela'),
        ('CO', 'Colombia'),
        ('PE', 'Perú'),
    )
    nombre_comercial = models.CharField(max_length=255, default="Mi Empresa", verbose_name="Nombre Comercial")
    razon_social = models.CharField(max_length=255, blank=True, null=True, verbose_name="Razón Social")
    rif = models.CharField(max_length=20, blank=True, null=True, verbose_name="RIF / ID Fiscal")
    telefono = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono de la Empresa", help_text="Número para recibir notificaciones de pedidos.")
    direccion = models.TextField(blank=True, null=True, verbose_name="Dirección Fiscal")
    logo = models.ImageField(upload_to='logos_empresas/', null=True, blank=True, verbose_name="Logo de la Empresa")
    pais_codigo = models.CharField(
        max_length=2, choices=PAIS_CHOICES, default='VE', verbose_name="País",
        help_text="País fiscal del tenant. Determina qué TaxStrategy (apps.configuracion.core.tax_strategy) se aplica por defecto.",
    )
    # Control de autorización para eliminar renglones (ej. un cajero
    # quitando un producto ya agregado al POS) -- apagado por defecto, el
    # admin lo activa si su negocio lo necesita. El PIN se guarda hasheado
    # (igual que una contraseña, ver `apps.configuracion.services.pin_service`)
    # -- nunca en texto plano, y nunca se devuelve en ninguna respuesta.
    requiere_pin_eliminar = models.BooleanField(
        default=False,
        verbose_name="Exigir PIN para eliminar renglones",
        help_text="Si está activo, eliminar un renglón (ítem del POS, de una mesa, etc.) exige este PIN antes de aplicarse -- para negocios que no dejan al cajero quitar un producto sin autorización.",
    )
    pin_autorizacion_hash = models.CharField(max_length=128, blank=True, null=True, verbose_name="PIN de autorización (hash)")
    # Mensaje que acompaña el link de WhatsApp al cerrar una venta -- cada
    # negocio quiere su propio tono/despedida. El link al PDF (ver
    # `apps.facturacion.api.views_impresion.FacturaLinkCompartirView`) NO
    # es parte de esta plantilla a propósito: el frontend siempre lo agrega
    # al final del mensaje ya armado (`utils/whatsapp.ts`), así que no hay
    # forma de configurar un mensaje que "olvide" mandar la factura --
    # wa.me no permite adjuntar el PDF directamente, el link es la única
    # manera de que en verdad le llegue.
    MENSAJE_WHATSAPP_VENTA_DEFAULT = "Hola {cliente}, gracias por tu compra{factura}. Total: {moneda} {total}. ¡Que la disfrutes!"
    mensaje_whatsapp_venta = models.TextField(
        blank=True, default=MENSAJE_WHATSAPP_VENTA_DEFAULT,
        verbose_name="Mensaje de WhatsApp al cerrar una venta",
        help_text=(
            "Variables disponibles: {cliente}, {factura} (correlativo entre paréntesis, o vacío), "
            "{total}, {moneda}. El link al PDF de la factura se agrega siempre al final, no se configura aquí."
        ),
    )

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
