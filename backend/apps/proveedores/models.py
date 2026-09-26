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
    Una factura/nota de un proveedor que le debemos -- se crea sola cuando
    se registra una compra con proveedor (ver
    `apps.inventario.services.stock_service.crear_y_aplicar_ajuste` y
    `apps.proveedores.core.proveedores_service.crear_cuenta_por_pagar_desde_ajuste`),
    igual que una venta a crédito genera su propio saldo en Cuentas por
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
    Se recibe en uno o varios lotes (`registrar_recepcion_orden_compra`):
    cada recepción genera su propio `AjusteInventario` de entrada (con lo
    que ya se descuenta/paga solo, ver `CuentaPorPagar`), así que una orden
    de compra no duplica esa lógica -- solo agrega el paso previo de "esto
    es lo que pedí" para poder comparar contra "esto es lo que en verdad
    llegó" línea por línea.
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