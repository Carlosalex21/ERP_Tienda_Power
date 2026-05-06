from decimal import Decimal

from autoslug import AutoSlugField
from django.db import models
from django.contrib.auth.models import User

class Almacen(models.Model):
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


class Categoriaproducto(models.Model): #Listo
    nombre = models.CharField(unique=True, max_length=100)
    slug = AutoSlugField(populate_from="nombre")
    padre = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, # Si se borra el usuario, este campo queda nulo
        null=True, 
        blank=True,
        related_name="categorias_creadas"
    )

    class Meta:
        db_table = 'CategoriaProducto'


class Atributo(models.Model):
    nombre = models.CharField(max_length=80)


class ValorAtributo(models.Model):
    atributo = models.ForeignKey(
        Atributo, on_delete=models.CASCADE, 
        related_name='valores',)
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
    configuracion_iva = models.ForeignKey("configuracion.ConfiguracionIva", models.DO_NOTHING, blank=True, null=True)
    slug = models.CharField(unique=True, max_length=100, blank=True, null=True)
    sku = models.CharField(unique=True, max_length=100, blank=True, null=True, help_text="Código único de producto (SKU), usado para sincronizar con otras plataformas.")
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

    # Campo de eliminacion logica
    activo = models.BooleanField(default=True)

    @property
    def base_imponible(self):
        """
        Calcula el precio base (sin IVA) a partir del precio final.
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


class Reservastock(models.Model):
    producto = models.ForeignKey(Producto, models.DO_NOTHING, blank=True, null=True)
    almacen = models.ForeignKey(Almacen, models.DO_NOTHING, blank=True, null=True)
    cantidad = models.IntegerField()
    orden = models.ForeignKey("facturacion.Orden", models.DO_NOTHING, blank=True, null=True)
    valido_hasta = models.DateTimeField()
    fecha_creacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'ReservaStock'


class Transportista(models.Model):
    nombre = models.CharField(max_length=100)
    tipo_envio = models.CharField(max_length=50)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    precio_kg_adicional = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    tiempo_entrega = models.CharField(max_length=20)
    activo = models.BooleanField(blank=True, null=True)

    class Meta:
        db_table = 'Transportista'