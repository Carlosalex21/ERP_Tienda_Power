from django.db import models
from django.contrib.auth.models import User
from erp.utils.correlativo import obtener_configuracion_correlativo


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
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_global = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    iva_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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
        # LOGICA DE CORRELATIVO
        # Si la factura no tiene correlativo y su estado está cambiando a 'pagado' o 'pendiente'
        if not self.correlativo and self.estado in ['pagado', 'pendiente']:
            try:
                # Obtenemos y bloqueamos la configuracion
                config = obtener_configuracion_correlativo()
                config.current_number += 1
                
                # Generamos el nuevo correlativo
                nuevo_numero = str(config.current_number).zfill(config.number_length)
                self.correlativo = f"{config.prefijo}{nuevo_numero}"
                
                config.save()
            except Exception as e:
                print(f"ERROR: No se pudo generar el correlativo. {e}")
                pass

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