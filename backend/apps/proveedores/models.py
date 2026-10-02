from django.conf import settings
from django.db import models, transaction


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


class CuentaPorPagar(models.Model):
    """
    Una factura/nota de un proveedor que le debemos -- se crea sola al
    registrar una `FacturaCompra` (ver
    `apps.proveedores.core.facturas_compra_service`), igual que una venta a crédito genera su propio saldo en Cuentas por
    Cobrar (ver `apps.facturacion.services.pagos_service`) -- antes no había
    NINGÚN registro de qué compras seguían pendientes de pagarle al
    proveedor, solo el asiento contable agregado (sin desglose por
    documento/proveedor).
    """
    ESTADO_CHOICES = (
        ('pendiente', 'Pendiente'),
        ('pagada', 'Pagada'),
        ('anulada', 'Anulada'),
    )
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name='cuentas_por_pagar')
    numero_documento = models.CharField(max_length=100, blank=True, default='')
    fecha_emision = models.DateField()
    # Se calcula sola desde `proveedor.plazo_pago` (días de crédito) si está
    # configurado -- queda en blanco si el proveedor no tiene plazo definido.
    fecha_vencimiento = models.DateField(null=True, blank=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    monto_pagado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pendiente')
    # De dónde salió esta cuenta -- para poder rastrear hacia el documento de
    # compra original (nota de entrega/factura del proveedor).
    ajuste_origen = models.ForeignKey(
        'inventario.AjusteInventario', on_delete=models.SET_NULL, null=True, blank=True, related_name='cuentas_por_pagar',
    )
    # Desde el módulo de Compras, toda cuenta nace de una `FacturaCompra`
    # (`ajuste_origen` queda solo para las cuentas históricas creadas desde
    # Ajustes de Inventario, antes de que existiera ese módulo).
    factura_compra = models.ForeignKey(
        'proveedores.FacturaCompra', on_delete=models.SET_NULL, null=True, blank=True, related_name='cuentas_por_pagar',
    )
    observaciones = models.TextField(blank=True, default='')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'CuentaPorPagar'
        ordering = ['-fecha_emision']
        verbose_name = 'Cuenta por Pagar'
        verbose_name_plural = 'Cuentas por Pagar'

    def __str__(self) -> str:
        return f'{self.proveedor.nombre} - {self.numero_documento or "s/n"} ({self.monto})'

    @property
    def saldo_pendiente(self):
        return self.monto - self.monto_pagado


class PagoProveedor(models.Model):
    """Un abono/pago real contra una `CuentaPorPagar` -- puede haber varios hasta saldarla."""
    cuenta_por_pagar = models.ForeignKey(CuentaPorPagar, on_delete=models.PROTECT, related_name='pagos')
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    metodo_pago = models.ForeignKey('facturacion.MetodoPago', on_delete=models.SET_NULL, null=True, blank=True)
    referencia = models.CharField(max_length=100, blank=True, default='')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'PagoProveedor'
        ordering = ['-fecha']
        verbose_name = 'Pago a Proveedor'
        verbose_name_plural = 'Pagos a Proveedores'

    def __str__(self) -> str:
        return f'Pago {self.monto} - {self.cuenta_por_pagar}'


class OrdenCompra(models.Model):
    """
    Pedido formal a un proveedor -- lo que le pedimos, ANTES de que llegue.
    Se recibe en uno o varios lotes, cada uno con la `FacturaCompra` (o
    nota de entrega) que trae el proveedor: esa factura mueve el stock,
    crea la cuenta por pagar y va al Libro de Compras. La orden solo agrega
    el paso previo de "esto es lo que pedí" para poder comparar contra
    "esto es lo que en verdad llegó" línea por línea.
    """
    ESTADO_CHOICES = (
        ('borrador', 'Borrador'),
        ('enviada', 'Enviada al proveedor'),
        ('recibida_parcial', 'Recibida parcialmente'),
        ('recibida', 'Recibida completa'),
        ('cancelada', 'Cancelada'),
    )
    numero = models.CharField(max_length=20, unique=True, editable=False)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name='ordenes_compra')
    almacen = models.ForeignKey('inventario.Almacen', on_delete=models.SET_NULL, null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    observaciones = models.TextField(blank=True, default='')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_envio = models.DateTimeField(null=True, blank=True)
    fecha_recepcion_completa = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'OrdenCompra'
        ordering = ['-fecha_creacion']
        verbose_name = 'Orden de Compra'
        verbose_name_plural = 'Órdenes de Compra'

    def __str__(self) -> str:
        return f'OC-{self.numero} -- {self.proveedor.nombre}'

    def save(self, *args, **kwargs):
        if not self.numero:
            # Mismo patrón que `OrdenServicio.numero`/`AsientoContable.numero`
            # -- correlativo propio bloqueando la última fila para que dos
            # órdenes creadas casi al mismo tiempo no choquen.
            with transaction.atomic():
                ultimo = OrdenCompra.objects.select_for_update().order_by('-id').first()
                siguiente = (int(ultimo.numero) + 1) if (ultimo and ultimo.numero.isdigit()) else 1
                self.numero = str(siguiente).zfill(5)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


class OrdenCompraDetalle(models.Model):
    """Línea de una `OrdenCompra`: cuánto se pidió de un producto vs. cuánto ha llegado hasta ahora."""
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT)
    cantidad_pedida = models.PositiveIntegerField()
    cantidad_recibida = models.PositiveIntegerField(default=0)
    costo_unitario_esperado = models.DecimalField(max_digits=14, decimal_places=6, blank=True, null=True)

    class Meta:
        db_table = 'OrdenCompraDetalle'

    def __str__(self) -> str:
        return f'{self.cantidad_pedida} x {self.producto.nombre} (OC-{self.orden.numero})'

    @property
    def cantidad_pendiente(self) -> int:
        return max(self.cantidad_pedida - self.cantidad_recibida, 0)


class FacturaCompra(models.Model):
    """
    Documento de compra recibido de un proveedor -- la factura fiscal (o la
    nota de entrega, cuando el proveedor no factura) con la que entra la
    mercancía. Es el ÚNICO camino por el que una compra mueve inventario,
    crea su `CuentaPorPagar`, se asienta en contabilidad y (si es factura
    fiscal) aparece en el Libro de Compras -- ver
    `apps.proveedores.core.facturas_compra_service.registrar_factura_compra`.

    Antes todo esto se cargaba como un "Ajuste de Inventario" con motivo
    "compra": el ajuste no tenía base/IVA, así que el Libro de Compras nunca
    se llenaba y el IVA crédito fiscal no existía en ningún lado. Los
    ajustes quedan ahora solo para movimientos internos (conteo, merma...).
    """
    TIPO_DOCUMENTO_CHOICES = (
        ('factura', 'Factura fiscal'),
        ('nota_entrega', 'Nota de entrega (sin factura)'),
    )
    ESTADO_CHOICES = (
        ('registrada', 'Registrada'),
        ('anulada', 'Anulada'),
    )
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name='facturas_compra')
    tipo_documento = models.CharField(max_length=15, choices=TIPO_DOCUMENTO_CHOICES, default='factura')
    numero_factura = models.CharField(max_length=50, help_text='Número de la factura (o de la nota de entrega) del proveedor.')
    numero_control = models.CharField(max_length=50, blank=True, default='', help_text='Número de control SENIAT impreso en la factura del proveedor.')
    fecha_emision = models.DateField(help_text='Fecha impresa en el documento del proveedor.')
    orden_compra = models.ForeignKey(OrdenCompra, on_delete=models.SET_NULL, null=True, blank=True, related_name='facturas')
    almacen = models.ForeignKey('inventario.Almacen', on_delete=models.SET_NULL, null=True, blank=True)
    # Montos en la moneda base del tenant (la misma del Libro de Compras y de
    # los costos de inventario).
    monto_exento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    base_imponible = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    iva = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Sumas de los comprobantes de retención emitidos sobre esta factura
    # (ver `Retencion.factura_compra`) -- se recalculan solas, no se editan.
    retencion_iva = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    retencion_islr = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ajuste = models.ForeignKey(
        'inventario.AjusteInventario', on_delete=models.SET_NULL, null=True, blank=True, related_name='facturas_compra',
        help_text='Entrada de inventario generada por esta compra.',
    )
    asiento = models.ForeignKey(
        'contabilidad.AsientoContable', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default='registrada')
    observaciones = models.TextField(blank=True, default='')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_anulacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'FacturaCompra'
        ordering = ['-fecha_emision', '-id']
        verbose_name = 'Factura de Compra'
        verbose_name_plural = 'Facturas de Compra'
        constraints = [
            # Un proveedor no puede emitir dos veces el mismo número -- evita
            # cargar la misma factura dos veces (doble stock, doble deuda).
            models.UniqueConstraint(
                fields=['proveedor', 'tipo_documento', 'numero_factura'],
                condition=models.Q(estado='registrada'),
                name='uniq_factura_compra_proveedor_numero',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.get_tipo_documento_display()} {self.numero_factura} -- {self.proveedor.nombre}'

    @property
    def total_retenido(self):
        return (self.retencion_iva or 0) + (self.retencion_islr or 0)

    @property
    def neto_a_pagar(self):
        return (self.total or 0) - self.total_retenido


class FacturaCompraDetalle(models.Model):
    """Línea de producto de una `FacturaCompra` -- costo unitario SIN IVA (el IVA es crédito fiscal, no costo)."""
    factura = models.ForeignKey(FacturaCompra, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT)
    variante = models.ForeignKey('inventario.Variacionproducto', on_delete=models.PROTECT, null=True, blank=True)
    orden_detalle = models.ForeignKey(OrdenCompraDetalle, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    cantidad = models.PositiveIntegerField()
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=6)

    class Meta:
        db_table = 'FacturaCompraDetalle'

    @property
    def subtotal(self):
        return self.cantidad * self.costo_unitario