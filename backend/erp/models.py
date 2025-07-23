from django.db import models, transaction
from django.conf import settings
from autoslug import AutoSlugField # type: ignore
from django.contrib.auth.models import User
from decimal import Decimal
from .utils.correlativo import obtener_configuracion_correlativo


class Almacen(models.Model): #Listo
    ESTADOS_CHOICES = (
        ('AND', 'Andalucía'),
        ('ARA', 'Aragón'),
        ('AST', 'Asturias'),
        ('BAL', 'Baleares'),
        ('CAN', 'Canarias'),
        ('CANT', 'Cantabria'),
        ('CLM', 'Castilla-La Mancha'),
        ('CYL', 'Castilla y León'),
        ('CAT', 'Cataluña'),
        ('EXT', 'Extremadura'),
        ('GAL', 'Galicia'),
        ('RIA', 'La Rioja'),
        ('MAD', 'Madrid'),
        ('MUR', 'Murcia'),
        ('NAV', 'Navarra'),
        ('PV', 'País Vasco'),
        ('VAL', 'Valencia'),
    )
    nombre = models.CharField(max_length=100)
    direccion = models.TextField()
    telefono = models.CharField(max_length=15, blank=True, null=True)
    activo = models.BooleanField(default=True)
    estado = models.CharField(max_length=4, choices=ESTADOS_CHOICES, default='CYL', blank=True, null=True)

    class Meta:
        db_table = 'Almacen'



class Carrito(models.Model):
    usuario = models.ForeignKey("UserMetadata", models.DO_NOTHING, blank=True, null=True)
    producto = models.ForeignKey('Producto', models.DO_NOTHING, blank=True, null=True)
    cantidad = models.IntegerField(blank=True, null=True)
    fecha_actualizacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Carrito'


class Categoriaproducto(models.Model): #Listo
    nombre = models.CharField(unique=True, max_length=100)
    slug = AutoSlugField(populate_from="nombre")
    padre = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'CategoriaProducto'


class Cliente(models.Model): #listo
    tipo_documento = models.CharField(max_length=10)
    documento = models.CharField(max_length=20)
    nombre = models.CharField(max_length=100)
    email = models.CharField(unique=True, max_length=254)
    telefono = models.CharField(max_length=15, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    codigo_postal = models.CharField(max_length=5, blank=True, null=True)
    provincia = models.CharField(max_length=50, blank=True, null=True)
    fecha_registro = models.DateTimeField(blank=True, null=True)
    usuario = models.ForeignKey('UserMetadata', models.DO_NOTHING, blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Cliente'
        unique_together = (('tipo_documento', 'documento'),)

    def __str__(self):
        return self.nombre


class Configuracioniva(models.Model):
    nombre = models.CharField(max_length=20, blank=True, null=True)
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2)
    activo = models.BooleanField(blank=True, null=True, default=True)
    fecha_creacion = models.DateTimeField(blank=True, null=True)
    

    class Meta:
        db_table = 'ConfiguracionIVA'


class Consentimientousuario(models.Model):
    usuario = models.ForeignKey('UserMetadata', models.DO_NOTHING, blank=True, null=True)
    tipo_consentimiento = models.CharField(max_length=50)
    version = models.TextField()
    fecha_aceptacion = models.DateTimeField(blank=True, null=True)
    ip_aceptacion = models.GenericIPAddressField()

    class Meta:
        db_table = 'ConsentimientoUsuario'


class Contabilidad(models.Model):
    tipo_asiento = models.CharField(max_length=20)
    fecha = models.DateField()
    concepto = models.TextField()
    debe = models.DecimalField(max_digits=10, decimal_places=2)
    haber = models.DecimalField(max_digits=10, decimal_places=2)
    factura = models.ForeignKey('Factura', models.DO_NOTHING, blank=True, null=True)
    pedido_proveedor = models.ForeignKey('Pedidoproveedor', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'Contabilidad'


class Cupondescuento(models.Model):
    codigo = models.CharField(unique=True, max_length=20)
    tipo = models.CharField(max_length=15)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    valido_desde = models.DateField()
    valido_hasta = models.DateField()
    usos_maximos = models.IntegerField(blank=True, null=True)
    usos_actuales = models.IntegerField(blank=True, null=True)
    minimo_compra = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    solo_categoria = models.ForeignKey(Categoriaproducto, models.DO_NOTHING, blank=True, null=True)
    solo_almacen = models.ForeignKey(Almacen, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'CuponDescuento'


class Detallefactura(models.Model):
    factura = models.ForeignKey('Factura', models.DO_NOTHING, blank=True, null=True)
    producto = models.ForeignKey('Producto', models.DO_NOTHING, blank=True, null=True)
    variante = models.ForeignKey('Variacionproducto', on_delete=models.CASCADE, null=True, blank=True)
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    subtotal_linea = models.DecimalField(max_digits=10, decimal_places=2)
    iva_linea = models.DecimalField(max_digits=10, decimal_places=2)
    total_linea = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'DetalleFactura'


class Devolucion(models.Model):
    orden = models.ForeignKey('Orden', models.DO_NOTHING, blank=True, null=True)
    motivo = models.TextField()
    estado = models.CharField(max_length=20, blank=True, null=True)
    monto_reembolso = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fecha_solicitud = models.DateTimeField(blank=True, null=True)
    fecha_resolucion = models.DateTimeField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Devolucion'


class Direccionenvio(models.Model):
    cliente = models.ForeignKey(Cliente, models.DO_NOTHING, blank=True, null=True)
    alias = models.CharField(max_length=50)
    direccion = models.TextField()
    codigo_postal = models.CharField(max_length=5)
    provincia = models.CharField(max_length=50)
    telefono_contacto = models.CharField(max_length=15)
    predeterminada = models.BooleanField(blank=True, null=True)

    class Meta:
        db_table = 'DireccionEnvio'


class Envio(models.Model):
    orden = models.ForeignKey('Orden', models.DO_NOTHING, blank=True, null=True)
    almacen = models.ForeignKey(Almacen, models.DO_NOTHING, blank=True, null=True)
    direccion = models.TextField()
    transportista = models.CharField(max_length=100, blank=True, null=True)
    numero_seguimiento = models.CharField(max_length=100, blank=True, null=True)
    costo = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    estado = models.CharField(max_length=50, blank=True, null=True)
    fecha_envio = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Envio'


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
    cliente = models.ForeignKey(Cliente, models.DO_NOTHING, blank=True, null=True)
    orden = models.OneToOneField('Orden', models.DO_NOTHING, blank=True, null=True)
    fecha_operacion = models.DateTimeField()
    correlativo = models.CharField(unique=True, max_length=50, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    descuento_global = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    iva_total = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    almacen = models.ForeignKey(Almacen, models.DO_NOTHING, blank=True, null=True)
    estado = models.CharField(max_length=20, blank=True, null=True)
    metodo_pago = models.ForeignKey(MetodoPago, models.DO_NOTHING, blank=True, null=True)
    nif_factura = models.CharField(max_length=20, blank=True, null=True)
    activo = models.BooleanField(default=True)
    nombre_cliente_pendiente = models.CharField(max_length=100, blank=True, null=True)
    comentario_pendiente = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'Factura'

    def save(self, *args, **kwargs):
        # --- LÓGICA DE CORRELATIVO CENTRALIZADA ---
        # Si la factura no tiene correlativo y su estado está cambiando a 'pagado' o 'pendiente'
        if not self.correlativo and self.estado in ['pagado', 'pendiente']:
            try:
                # Obtenemos y bloqueamos la configuración para evitar condiciones de carrera
                config = obtener_configuracion_correlativo()
                config.current_number += 1
                
                # Generamos el nuevo correlativo
                nuevo_numero = str(config.current_number).zfill(config.number_length)
                self.correlativo = f"{config.prefijo}{nuevo_numero}"
                
                config.save()
            except Exception as e:
                print(f"ERROR: No se pudo generar el correlativo. {e}")
                # Dependiendo de tu lógica de negocio, podrías querer evitar que se guarde
                # o simplemente registrar el error. Por ahora, lo dejamos continuar.
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


class Inventario(models.Model): #Listo
    producto = models.ForeignKey('Producto', models.SET_NULL, blank=True, null=True)
    almacen = models.ForeignKey(Almacen, models.SET_NULL, blank=True, null=True,)
    cantidad = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Inventario'
        unique_together = (('producto', 'almacen'),)


class MovimientoInventario(models.Model):
    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE)
    tipo_movimiento = models.CharField(choices=[('entrada', 'Entrada'), ('salida', 'Salida')], max_length=10)
    cantidad = models.ForeignKey('Producto', models.SET_NULL, blank=True, null=True)
    stock_minimo = models.IntegerField(blank=True, null=True)
    fecha_movimiento = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'MovimientoInventario'



class Lecturacodigobarras(models.Model):
    codigo_barras = models.CharField(max_length=50)
    fecha_lectura = models.DateTimeField(blank=True, null=True)
    almacen = models.ForeignKey(Almacen, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'LecturaCodigoBarras'


class Logactividad(models.Model):
    usuario = models.ForeignKey('UserMetadata', models.DO_NOTHING, blank=True, null=True)
    accion = models.CharField(max_length=100)
    detalles = models.TextField(blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'LogActividad'


class ConfiguracionCorrelativo(models.Model):
    prefijo = models.CharField(max_length=10, default="F-")
    current_number = models.IntegerField(default=0)
    number_length = models.IntegerField(default=3)  # Por ejemplo, 3 para mostrar 028, 150, etc.

    class Meta:
        db_table = 'ConfiguracionCorrelativo'

    def get_next_correlativo(self):
        # Manejamos la actualización de forma atómica para evitar duplicados
        with transaction.atomic():
            # Bloqueamos la fila para evitar condiciones de carrera
            config = ConfiguracionCorrelativo.objects.select_for_update().get(id=self.id)
            config.current_number += 1
            config.save()
            # Se aplica el formato, rellenando con ceros a la izquierda según la longitud requerida.
            number_str = str(config.current_number).zfill(config.number_length)
            return f"{config.prefijo}{number_str}"

class Orden(models.Model):
    usuario = models.ForeignKey('UserMetadata', models.DO_NOTHING, blank=True, null=True)
    cliente = models.ForeignKey(Cliente, models.DO_NOTHING, blank=True, null=True)
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



class Pedidoproveedor(models.Model):
    proveedor = models.ForeignKey('Proveedor', models.DO_NOTHING, blank=True, null=True)
    fecha_pedido = models.DateField(blank=True, null=True)
    fecha_esperada = models.DateField()
    estado = models.CharField(max_length=20, blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'PedidoProveedor'


class Atributo(models.Model):
    nombre = models.CharField(max_length=80)

class ValorAtributo(models.Model):
    atributo = models.ForeignKey(Atributo, on_delete=models.CASCADE)
    valor = models.CharField(max_length=80) 

class Producto(models.Model): #Listo
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    cantidad = models.IntegerField(blank=True, null=True)
    almacen = models.ForeignKey(Almacen, on_delete=models.SET_NULL, blank=True, null=True)
    codigo_barras = models.CharField(unique=True, max_length=50, blank=True, null=True)
    disponible_online = models.BooleanField(blank=True, null=True)
    descuento = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    configuracion_iva = models.ForeignKey(Configuracioniva, models.DO_NOTHING, blank=True, null=True)
    slug = models.CharField(unique=True, max_length=100, blank=True, null=True)
    peso = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    dimensiones = models.CharField(max_length=50, blank=True, null=True)
    categoria = models.ForeignKey(Categoriaproducto, on_delete=models.SET_NULL,blank=True, null=True)
    # Campo para la imagen; upload_to indica la subcarpeta dentro de MEDIA_ROOT donde se guardará
    imagen = models.ImageField(upload_to='productos/', blank=True, null=True)
    TIPO_CHOICES = (
        ('simple', 'Simple'),
        ('variable', 'Variable'),
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='simple')

    #Campo de eliminacion logica
    activo = models.BooleanField(default=True)

    @property
    def base_imponible(self):
        """
        Calcula el precio base (sin IVA) a partir del precio final.
        Ejemplo: si el precio final es 55 y el IVA es 10%, devuelve 50.
        """
        if self.precio and self.configuracion_iva:
            tasa_iva = self.configuracion_iva.porcentaje_iva
            if tasa_iva > 0:
                # Cálculo inverso: Base = Total / (1 + Tasa)
                base = self.precio / (Decimal("1") + tasa_iva / Decimal("100"))
                return base
        return self.precio


    class Meta:
        db_table = 'Producto'


class Productocategoria(models.Model):
    producto = models.ForeignKey(Producto, models.DO_NOTHING, blank=True, null=True)
    categoria = models.ForeignKey(Categoriaproducto, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ProductoCategoria'
        unique_together = (('producto', 'categoria'),)


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


class Proveedor(models.Model):
    cif = models.CharField(unique=True, max_length=10)
    nombre = models.CharField(max_length=100)
    direccion = models.TextField()
    telefono = models.CharField(max_length=15, blank=True, null=True)
    email = models.CharField(max_length=254)
    plazo_pago = models.IntegerField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Proveedor'


class Reportecliente(models.Model):
    cliente = models.ForeignKey(Cliente, models.DO_NOTHING, blank=True, null=True)
    total_compras = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_pedidos = models.IntegerField()
    producto_mas_comprado = models.ForeignKey(Producto, models.DO_NOTHING, db_column='producto_mas_comprado', blank=True, null=True)

    class Meta:
        db_table = 'ReporteCliente'


class Reporteinventario(models.Model):
    fecha = models.DateField()
    producto = models.ForeignKey(Producto, models.DO_NOTHING, blank=True, null=True)
    stock_inicial = models.IntegerField()
    stock_final = models.IntegerField()
    movimientos = models.IntegerField()
    almacen = models.ForeignKey(Almacen, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ReporteInventario'


class Reporteventa(models.Model):
    fecha = models.DateField()
    total_ventas = models.DecimalField(max_digits=12, decimal_places=2)
    total_iva = models.DecimalField(max_digits=12, decimal_places=2)
    total_descuentos = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_transacciones = models.IntegerField()
    almacen = models.ForeignKey(Almacen, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ReporteVenta'


class Resenaproducto(models.Model):
    producto = models.ForeignKey(Producto, models.DO_NOTHING, blank=True, null=True)
    usuario = models.ForeignKey('UserMetadata', models.DO_NOTHING, blank=True, null=True)
    calificacion = models.IntegerField()
    comentario = models.TextField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'ResenaProducto'


class Reservastock(models.Model):
    producto = models.ForeignKey(Producto, models.DO_NOTHING, blank=True, null=True)
    almacen = models.ForeignKey(Almacen, models.DO_NOTHING, blank=True, null=True)
    cantidad = models.IntegerField()
    orden = models.ForeignKey(Orden, models.DO_NOTHING, blank=True, null=True)
    valido_hasta = models.DateTimeField()
    fecha_creacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'ReservaStock'


class Rol(models.Model):
    nombre = models.CharField(unique=True, max_length=50)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Rol'

    def __str__(self):
        return self.nombre


class Sesionusuario(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    datos = models.TextField()
    fecha_actualizacion = models.DateTimeField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'SesionUsuario'


class Tipodocumentofiscal(models.Model):
    codigo = models.CharField(unique=True, max_length=10)
    descripcion = models.CharField(max_length=100)
    obligatorio = models.BooleanField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'TipoDocumentoFiscal'

    def __str__(self):
        return self.codigo


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


class Transportista(models.Model):
    nombre = models.CharField(max_length=100)
    tipo_envio = models.CharField(max_length=50)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    precio_kg_adicional = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    tiempo_entrega = models.CharField(max_length=20)
    activo = models.BooleanField(blank=True, null=True)

    class Meta:
        db_table = 'Transportista'


class UserMetadata(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="metadata")
    rol = models.ForeignKey('Rol', models.DO_NOTHING, blank=True, null=True)
    telefono = models.CharField(max_length=15, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    ultimo_login = models.DateTimeField(blank=True, null=True)
    
    # Datos personales
    nombre = models.CharField(max_length=100, blank=True, null=True)
    apellido = models.CharField(max_length=100, default="N/A")
    tipo_documento = models.ForeignKey('Tipodocumentofiscal', models.SET_NULL, null=True, blank=True)
    numero_documento = models.CharField(max_length=30, blank=True, null=True)
    correo = models.EmailField(max_length=254, unique=True, blank=True, null=True)
    
    # Estado y seguridad
    es_activo = models.BooleanField(default=True)
    verificado = models.BooleanField(default=False)
    token_verificacion = models.CharField(max_length=64, blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'UserMetadata'

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.user.username})"


def variant_image_upload_to(instance, filename):
    product_slug = instance.producto.slug if instance.producto and instance.producto.slug else "default"
    # Forma la ruta: productos/<slug>/variaciones/<filename>
    return f"productos/{product_slug}/variaciones/{filename}"


class Variacionproducto(models.Model):
    producto = models.ForeignKey(Producto, models.DO_NOTHING, blank=True, null=True)
    atributos = models.ManyToManyField(ValorAtributo)
    nombre = models.CharField(max_length=80)
    sku = models.CharField(unique=True, max_length=50, blank=True, null=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    cantidad = models.IntegerField(blank=True, null=True)
    codigo_barras = models.CharField(max_length=50, unique=True, null=True)
    # Campo para la imagen; upload_to indica la subcarpeta dentro de MEDIA_ROOT donde se guardará
    imagen = models.ImageField(upload_to=variant_image_upload_to, blank=True, null=True)

    class Meta:
        db_table = 'VariacionProducto'


# class AuthGroup(models.Model):
#     name = models.CharField(unique=True, max_length=150)

#     class Meta:
#         managed = False
#         db_table = 'auth_group'


# class AuthGroupPermissions(models.Model):
#     id = models.BigAutoField(primary_key=True)
#     group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
#     permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

#     class Meta:
#         managed = False
#         db_table = 'auth_group_permissions'
#         unique_together = (('group', 'permission'),)


# class AuthPermission(models.Model):
#     name = models.CharField(max_length=255)
#     content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
#     codename = models.CharField(max_length=100)

#     class Meta:
#         managed = False
#         db_table = 'auth_permission'
#         unique_together = (('content_type', 'codename'),)


# class AuthUser(models.Model):
#     password = models.CharField(max_length=128)
#     last_login = models.DateTimeField(blank=True, null=True)
#     is_superuser = models.BooleanField()
#     username = models.CharField(unique=True, max_length=150)
#     first_name = models.CharField(max_length=150)
#     last_name = models.CharField(max_length=150)
#     email = models.CharField(max_length=254)
#     is_staff = models.BooleanField()
#     is_active = models.BooleanField()
#     date_joined = models.DateTimeField()

#     class Meta:
#         managed = False
#         db_table = 'auth_user'


# class AuthUserGroups(models.Model):
#     id = models.BigAutoField(primary_key=True)
#     user = models.ForeignKey(AuthUser, models.DO_NOTHING)
#     group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

#     class Meta:
#         managed = False
#         db_table = 'auth_user_groups'
#         unique_together = (('user', 'group'),)


# class AuthUserUserPermissions(models.Model):
#     id = models.BigAutoField(primary_key=True)
#     user = models.ForeignKey(AuthUser, models.DO_NOTHING)
#     permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

#     class Meta:
#         managed = False
#         db_table = 'auth_user_user_permissions'
#         unique_together = (('user', 'permission'),)


# class DjangoAdminLog(models.Model):
#     action_time = models.DateTimeField()
#     object_id = models.TextField(blank=True, null=True)
#     object_repr = models.CharField(max_length=200)
#     action_flag = models.SmallIntegerField()
#     change_message = models.TextField()
#     content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
#     user = models.ForeignKey(AuthUser, models.DO_NOTHING)

#     class Meta:
#         managed = False
#         db_table = 'django_admin_log'


# class DjangoContentType(models.Model):
#     app_label = models.CharField(max_length=100)
#     model = models.CharField(max_length=100)

#     class Meta:
#         managed = False
#         db_table = 'django_content_type'
#         unique_together = (('app_label', 'model'),)



# class DjangoSession(models.Model):
#     session_key = models.CharField(primary_key=True, max_length=40)
#     session_data = models.TextField()
#     expire_date = models.DateTimeField()

#     class Meta:
#         managed = False
#         db_table = 'django_session'
