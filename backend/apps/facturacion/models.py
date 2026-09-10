from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User

from apps.configuracion.core.config_service import (
    obtener_y_actualizar_correlativo,
    obtener_y_actualizar_numero_control,
)


class MetodoPago(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    nro_cuenta = models.CharField(max_length=50, blank=True, null=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    tipo_metodo = models.CharField(max_length=20, blank=True, null=True)
    activo = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'MetodoPago'

    def __str__(self):
        return self.nombre
    

class Factura(models.Model):
    usuario = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="facturas_creadas"
    )
    cliente = models.ForeignKey("clientes.Cliente", models.DO_NOTHING, blank=True, null=True)
    orden = models.OneToOneField('Orden', models.DO_NOTHING, blank=True, null=True)
    fecha_operacion = models.DateTimeField()
    correlativo = models.CharField(unique=True, max_length=50, blank=True, null=True)
    # --- Campos SENIAT ---
    numero_control = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Control", help_text="Número de control SENIAT de la factura.")
    base_imponible = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Base Imponible")
    retencion_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Retención Total")
    # --- Multi-moneda ---
    moneda = models.ForeignKey("configuracion.Moneda", models.DO_NOTHING, blank=True, null=True, verbose_name="Moneda")
    tasa_cambio = models.DecimalField(max_digits=20, decimal_places=6, blank=True, null=True, verbose_name="Tasa de Cambio", help_text="Tasa aplicada a la moneda de la factura frente a la base.")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_global = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    iva_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # --- Consolidación en moneda base (para reportes) ---
    subtotal_base = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Subtotal (Base)")
    base_imponible_base = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Base Imponible (Base)")
    iva_base = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="IVA (Base)")
    retencion_base = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Retención (Base)")
    total_base = models.DecimalField(max_digits=14, decimal_places=2, default=0, verbose_name="Total (Base)")

    almacen = models.ForeignKey("inventario.Almacen", models.DO_NOTHING, blank=True, null=True)


    estado = models.CharField(max_length=20, blank=True, null=True)
    metodo_pago = models.ForeignKey(MetodoPago, models.DO_NOTHING, blank=True, null=True)
    nif_factura = models.CharField(max_length=20, blank=True, null=True)
    activo = models.BooleanField(default=True)
    nombre_cliente_pendiente = models.CharField(max_length=100, blank=True, null=True)
    comentario_pendiente = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'Factura'

    def save(self, *args, **kwargs):
        # LÓGICA DE CORRELATIVO Y NÚMERO DE CONTROL (SENIAT).
        #
        # El número de factura y el número de control se generan de forma
        # atómica (SELECT ... FOR UPDATE) para evitar condiciones de carrera
        # al emitir la factura, ya sea en estado 'pagado' o 'pendiente'.
        if not self.correlativo and self.estado in ['pagado', 'pendiente']:
            try:
                self.correlativo = obtener_y_actualizar_correlativo()
            except Exception as e:
                # No propagamos el error para no bloquear la emisión, pero
                # dejamos constancia en el log del servidor.
                import logging
                logging.getLogger(__name__).error(
                    "No se pudo generar el correlativo de la factura: %s", e
                )

        # Número de control SENIAT (se genera junto al correlativo).
        if not self.numero_control and self.estado in ['pagado', 'pendiente']:
            try:
                self.numero_control = obtener_y_actualizar_numero_control()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    "No se pudo generar el número de control de la factura: %s", e
                )

        super().save(*args, **kwargs)





class Facturaelectronica(models.Model):
    factura = models.OneToOneField(Factura, models.DO_NOTHING, blank=True, null=True)
    csv = models.CharField(max_length=50)
    qr_code = models.BinaryField()
    firma_electronica = models.TextField()
    fecha_registro_aeat = models.DateTimeField()
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'FacturaElectronica'


class Cupondescuento(models.Model):
    codigo = models.CharField(unique=True, max_length=20)
    tipo = models.CharField(max_length=15)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    valido_desde = models.DateField()
    valido_hasta = models.DateField()
    usos_maximos = models.IntegerField(blank=True, null=True)
    usos_actuales = models.IntegerField(blank=True, null=True)
    minimo_compra = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    solo_categoria = models.ForeignKey("inventario.Categoriaproducto", models.DO_NOTHING, blank=True, null=True)
    solo_almacen = models.ForeignKey("inventario.Almacen", models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'CuponDescuento'


class Detallefactura(models.Model):
    factura = models.ForeignKey(Factura, models.CASCADE, blank=True, null=True, related_name='detalles')
    producto = models.ForeignKey('inventario.Producto', models.DO_NOTHING, blank=True, null=True)
    variante = models.ForeignKey('inventario.Variacionproducto', on_delete=models.CASCADE, null=True, blank=True)
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    subtotal_linea = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    iva_linea = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_linea = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        db_table = 'DetalleFactura'


class Orden(models.Model):
    usuario = models.ForeignKey('usuarios.UserMetadata', models.DO_NOTHING, blank=True, null=True)
    cliente = models.ForeignKey("clientes.Cliente", models.DO_NOTHING, blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_operacion = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=20)  # "abierta", "cerrada", "pagada", etc.
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_producto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    iva_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    direccion_envio = models.TextField(blank=True, null=True)
    metodo_pago = models.ForeignKey(MetodoPago, models.DO_NOTHING, blank=True, null=True)
    transaccion_id = models.CharField(max_length=100, blank=True, null=True)
    activo = models.BooleanField(default=True)
    correlativo = models.CharField(max_length=50, unique=True, blank=True, null=True)

    class Meta:
        db_table = 'Orden'


class Devolucion(models.Model):
    orden = models.ForeignKey(Orden, models.DO_NOTHING, blank=True, null=True)
    motivo = models.TextField()
    estado = models.CharField(max_length=20, blank=True, null=True)
    monto_reembolso = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fecha_solicitud = models.DateTimeField(blank=True, null=True)
    fecha_resolucion = models.DateTimeField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Devolucion'


class Direccionenvio(models.Model):
    cliente = models.ForeignKey("clientes.Cliente", models.DO_NOTHING, blank=True, null=True)
    alias = models.CharField(max_length=50)
    direccion = models.TextField()
    codigo_postal = models.CharField(max_length=5)
    provincia = models.CharField(max_length=50)
    telefono_contacto = models.CharField(max_length=15)
    predeterminada = models.BooleanField(blank=True, null=True)

    class Meta:
        db_table = 'DireccionEnvio'


class Envio(models.Model):
    orden = models.ForeignKey(Orden, models.DO_NOTHING, blank=True, null=True)
    almacen = models.ForeignKey("inventario.Almacen", models.DO_NOTHING, blank=True, null=True)
    direccion = models.TextField()
    transportista = models.CharField(max_length=100, blank=True, null=True)
    numero_seguimiento = models.CharField(max_length=100, blank=True, null=True)
    costo = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    estado = models.CharField(max_length=50, blank=True, null=True)
    fecha_envio = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Envio'


class Transaccionpago(models.Model):
    orden = models.ForeignKey(Orden, models.DO_NOTHING, blank=True, null=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.ForeignKey(MetodoPago, models.DO_NOTHING, blank=True, null=True)
    estado = models.CharField(max_length=20)
    codigo_transaccion = models.CharField(unique=True, max_length=100, blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'TransaccionPago'


class Promocion(models.Model):
    codigo = models.CharField(unique=True, max_length=50)
    tipo = models.CharField(max_length=20)
    valor = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    max_usos = models.IntegerField(blank=True, null=True)
    usos_actuales = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'Promocion'
class NotaCredito(models.Model):
    """
    Nota de Crédito emitida conforme a las providencias del SENIAT.

    Representa la anulación o devolución total/parcial de una factura,
    restando montos del débito fiscal del emisor.
    """
    factura = models.ForeignKey(
        Factura,
        models.DO_NOTHING,
        blank=True,
        null=True,
        related_name="notas_credito",
        verbose_name="Factura Asociada",
    )
    numero_nota = models.CharField(unique=True, max_length=50, verbose_name="Número de Nota")
    numero_control = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Control")
    fecha_emision = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Emisión")
    motivo = models.TextField(verbose_name="Motivo")
    base_imponible = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Base Imponible")
    iva_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="IVA")
    retencion_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Retención")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    activo = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        db_table = 'NotaCredito'
        verbose_name = "Nota de Crédito"
        verbose_name_plural = "Notas de Crédito"
        ordering = ['-fecha_emision']


class NotaDebito(models.Model):
    """
    Nota de Débito emitida conforme a las providencias del SENIAT.

    Incrementa el débito fiscal del emisor (recargos, intereses, diferencias).
    """
    factura = models.ForeignKey(
        Factura,
        models.DO_NOTHING,
        blank=True,
        null=True,
        related_name="notas_debito",
        verbose_name="Factura Asociada",
    )
    numero_nota = models.CharField(unique=True, max_length=50, verbose_name="Número de Nota")
    numero_control = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Control")
    fecha_emision = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Emisión")
    motivo = models.TextField(verbose_name="Motivo")
    base_imponible = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Base Imponible")
    iva_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="IVA")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    activo = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        db_table = 'NotaDebito'
        verbose_name = "Nota de Débito"
        verbose_name_plural = "Notas de Débito"
        ordering = ['-fecha_emision']


class LibroCompraVenta(models.Model):
    """
    Registro de los Libros de Compra y Venta exigidos por el SENIAT.

    Agrega una línea por cada factura, nota de crédito o nota de débito,
    separando las operaciones de compra (débito fiscal del comprador) y de
    venta (débito fiscal del vendedor).
    """
    TIPO_LIBRO_CHOICES = (
        ('compra', 'Libro de Compra'),
        ('venta', 'Libro de Venta'),
    )
    tipo_libro = models.CharField(max_length=10, choices=TIPO_LIBRO_CHOICES, verbose_name="Tipo de Libro")
    fecha_operacion = models.DateField(verbose_name="Fecha de Operación")
    tipo_documento = models.CharField(max_length=50, verbose_name="Tipo de Documento", help_text="Ej: Factura, Nota de Crédito, Nota de Débito")
    numero_documento = models.CharField(max_length=50, verbose_name="Número de Documento")
    numero_control = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Control")
    rif = models.CharField(max_length=20, blank=True, null=True, verbose_name="RIF")
    razon_social = models.CharField(max_length=255, verbose_name="Razón Social")
    base_imponible = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Base Imponible")
    iva = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="IVA")
    retencion = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Retención")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        db_table = 'LibroCompraVenta'
        verbose_name = "Libro de Compra y Venta"
        verbose_name_plural = "Libros de Compra y Venta"
        ordering = ['-fecha_operacion']
        indexes = [
            models.Index(fields=['tipo_libro', 'fecha_operacion'], name='idx_libro_fecha'),
        ]


class Retencion(models.Model):
    """
    Comprobante de retención (ISLR, IVA) emitido conforme al SENIAT.

    Registra el comprobante de retención asociado a una factura de compra,
    sirviendo de soporte para el crédito fiscal del contribuyente.
    """
    TIPO_RETENCION_CHOICES = (
        ('islr', 'ISLR'),
        ('iva', 'IVA Retenido'),
        ('otros', 'Otros'),
    )
    factura = models.ForeignKey(
        Factura,
        models.DO_NOTHING,
        blank=True,
        null=True,
        related_name="retenciones",
        verbose_name="Factura Asociada",
    )
    proveedor = models.ForeignKey(
        "proveedores.Proveedor",
        models.DO_NOTHING,
        blank=True,
        null=True,
        related_name="retenciones",
        verbose_name="Proveedor",
    )
    tipo_retencion = models.CharField(max_length=10, choices=TIPO_RETENCION_CHOICES, verbose_name="Tipo de Retención")
    numero_comprobante = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Comprobante")
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Porcentaje (%)")
    base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Base")
    monto = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Monto")
    fecha_emision = models.DateField(auto_now_add=True, verbose_name="Fecha de Emisión")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        db_table = 'Retencion'
        verbose_name = "Comprobante de Retención"
        verbose_name_plural = "Comprobantes de Retención"
        ordering = ['-fecha_emision']
