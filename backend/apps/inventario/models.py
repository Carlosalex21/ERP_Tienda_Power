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
    # Deprecado: hardcodeado a comunidades autónomas de España, incompatible
    # con tenants en Venezuela/Colombia/Perú. Se conserva (sin quitar datos
    # existentes) mientras se migra a `region`, que sí es multi-país.
    estado = models.CharField(max_length=4, choices=ESTADOS_CHOICES, default='CYL', blank=True, null=True)
    region = models.ForeignKey(
        'Region', on_delete=models.SET_NULL, blank=True, null=True,
        verbose_name="Región/Estado/Departamento",
        help_text="Reemplazo multi-país de `estado`. Usar este campo en instalaciones nuevas.",
    )

    class Meta:
        db_table = 'Almacen'


class Region(models.Model):
    """
    División administrativa (estado, departamento o provincia) de un país.

    Reemplaza el enfoque de `Almacen.ESTADOS_CHOICES` -- hardcodeado a las
    comunidades autónomas de España -- por un catálogo parametrizable por
    país, coherente con el resto del motor fiscal multi-país
    (``apps.configuracion.core.tax_strategy``).
    """
    PAIS_CHOICES = (
        ('VE', 'Venezuela'),
        ('CO', 'Colombia'),
        ('PE', 'Perú'),
    )
    pais_codigo = models.CharField(max_length=2, choices=PAIS_CHOICES, verbose_name="País")
    codigo = models.CharField(max_length=10, verbose_name="Código")
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Region'
        verbose_name = "Región"
        verbose_name_plural = "Regiones"
        unique_together = (('pais_codigo', 'codigo'),)
        ordering = ['pais_codigo', 'nombre']

    def __str__(self) -> str:
        return f"{self.nombre} ({self.pais_codigo})"


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
    # Costo promedio ponderado por unidad -- se recalcula solo en cada
    # ENTRADA con `costo_unitario` informado (ver
    # `stock_service.crear_y_aplicar_ajuste`); una salida NUNCA lo toca,
    # solo lo consume. Es lo único que permite valorizar el inventario y
    # calcular el Costo de Venta al generar el asiento automático de una
    # venta (ver `apps.contabilidad.services.generar_asiento_automatico_venta`)
    # -- sin esto, el sistema no tenía forma de saber cuánto vale lo vendido,
    # solo su precio de venta.
    costo_promedio = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    almacen = models.ForeignKey(Almacen, on_delete=models.SET_NULL, blank=True, null=True)
    # Qué equipo de trabajo prepara/despacha este producto (ej. "Cocina" para
    # un plato, "Barra" para un trago, "Almacén" para un artículo de
    # depósito) -- ver `apps.rrhh.models.Departamento`. Al agregarse a un
    # `PedidoMesaItem` este valor se copia como snapshot (ver
    # `apps.restaurantes.api.views.PedidoMesaViewSet.agregar_item`), así que
    # cambiarlo después no reescribe pedidos ya en curso.
    departamento = models.ForeignKey(
        'rrhh.Departamento', on_delete=models.SET_NULL, blank=True, null=True, related_name='+',
    )
    codigo_barras = models.CharField(unique=True, max_length=50, blank=True, null=True)
    disponible_online = models.BooleanField(blank=True, null=True)
    # Insumo/materia prima de uso interno (ej. papas, zanahoria en un
    # restaurante; un repuesto genérico en un taller): se compra y se
    # descuenta como cualquier producto, pero NO es algo que se ofrezca
    # directamente -- no debe aparecer en el selector de "agregar ítem" del
    # POS/Mesas (`disponible_online` ya lo excluye del catálogo público, pero
    # esa bandera no dice nada sobre si el propio personal debería poder
    # "venderlo" tal cual desde el mostrador).
    es_insumo = models.BooleanField(
        default=False,
        verbose_name="Es insumo interno",
        help_text="Ítem de stock que no se ofrece directamente (ej. materia prima) -- se excluye de los selectores de venta.",
    )
    descuento = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    configuracion_iva = models.ForeignKey("configuracion.ConfiguracionIva", models.DO_NOTHING, blank=True, null=True)
    # Moneda en la que está expresado `precio`. Antes no existía: el POS y el
    # catálogo público asumían que TODO producto estaba en la moneda base del
    # tenant, así que al cambiar de moneda en el POS el precio se re-etiquetaba
    # tal cual (ej. "20" pasaba de "$20" a "Bs 20") en vez de convertirse. Si
    # se deja sin asignar, se sigue interpretando como la moneda base (mismo
    # comportamiento que antes, para no romper productos ya existentes).
    moneda = models.ForeignKey(
        "configuracion.Moneda", models.SET_NULL, blank=True, null=True,
        related_name="productos",
        help_text="Moneda en la que se ingresó `precio`. Si se deja vacío, se asume la moneda base del tenant.",
    )
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
        # Algo que se cobra pero no es un ítem físico de inventario (ej.
        # "Servicio Técnico", "Mano de Obra", "Consulta") -- no tiene stock
        # que descontar (ver `afectar_inventario_por_venta`, que lo salta) ni
        # campos como almacén/código de barras/stock mínimo que no aplican.
        ('servicio', 'Servicio'),
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='simple')
    # Antes "bajo stock" (dashboard) usaba un umbral fijo (`cantidad < 10`)
    # igual para todo el catálogo -- sin sentido para un negocio que vende
    # tanto tornillos (bajo stock a los 500) como electrodomésticos (bajo
    # stock a los 2). Si se deja vacío, se sigue usando ese umbral global.
    stock_minimo = models.PositiveIntegerField(
        blank=True, null=True,
        help_text='Umbral de "bajo stock" para este producto. Vacío = usa el umbral general del sistema.',
    )
    # Vacío = este producto no lleva garantía rastreada -- no se genera
    # ninguna `Garantia` al venderlo (ver `apps.postventa.services`). Puesto
    # aquí (no en `apps.postventa`) porque es un atributo propio del
    # producto, igual que `stock_minimo`.
    meses_garantia = models.PositiveIntegerField(
        blank=True, null=True, verbose_name="Meses de Garantía",
        help_text='Cuántos meses de garantía tiene este producto al venderse. Vacío = sin garantía rastreada.',
    )

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

    def __str__(self) -> str:
        return self.nombre


class PresentacionProducto(models.Model):
    """
    Forma alternativa de vender un producto simple -- ej. "Unidad", "Caja
    x12", "Bulto x50" -- sin duplicar el stock: el inventario siempre se
    lleva en unidades base (`Producto.cantidad`); una presentación es solo
    un factor de conversión + un precio para esa forma de venderlo. Vender
    "2 Bulto x50" descuenta 100 unidades base del mismo stock que vender
    "100 Unidad" -- nunca se llevan contadores separados por presentación,
    para no poder desincronizarse entre sí.

    Solo aplica a productos `tipo='simple'` (no a productos con variantes,
    para no combinar dos ejes de complejidad -- talla/color y unidad/bulto
    -- en una primera versión).
    """
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='presentaciones')
    nombre = models.CharField(max_length=50, help_text='Ej: Unidad, Caja x12, Bulto x50.')
    # PositiveIntegerField (no Decimal): el stock base (`Producto.cantidad`)
    # es un entero, así que una presentación solo puede representar un
    # múltiplo entero de la unidad base para que la conversión sea exacta.
    factor_conversion = models.PositiveIntegerField(
        default=1,
        help_text='Cuántas unidades base equivale una unidad de esta presentación (ej: 50 para "Bulto x50").',
    )
    # Si se deja vacío, se autocalcula como `producto.precio * factor_conversion`
    # al momento de vender -- pero permitir fijarlo a mano es necesario porque
    # el precio por bulto casi nunca es exactamente proporcional (suele haber
    # descuento por volumen).
    precio = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        help_text='Precio final (con IVA incluido) de esta presentación. Vacío = precio unitario × factor.',
    )
    es_default = models.BooleanField(
        default=False,
        help_text='La presentación preseleccionada al vender (normalmente "Unidad", factor 1).',
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'PresentacionProducto'
        ordering = ['factor_conversion']

    def __str__(self) -> str:
        nombre_producto = getattr(self.producto, 'nombre', None)
        return f"{nombre_producto} - {self.nombre}" if nombre_producto else self.nombre


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
    costo_promedio = models.DecimalField(max_digits=14, decimal_places=6, default=0)
    # `blank=True` (antes faltaba): igual que en Producto, muchos rubros no
    # asignan código de barras a cada variante -- sin esto, DRF lo trataba
    # como obligatorio aunque el modelo ya lo permitía nulo.
    codigo_barras = models.CharField(max_length=50, unique=True, null=True, blank=True)
    # Campo para la imagen; upload_to indica la subcarpeta dentro de MEDIA_ROOT donde se guardará
    imagen = models.ImageField(upload_to=variant_image_upload_to, blank=True, null=True)
    # Baja lógica -- igual que `Producto.activo`. Necesario porque
    # `Detallefactura.variante` es PROTECT: una variante ya vendida no se
    # puede borrar de verdad, así que "eliminarla" solo puede significar
    # ocultarla.
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'VariacionProducto'

    def __str__(self) -> str:
        nombre_producto = getattr(self.producto, 'nombre', None)
        return f"{nombre_producto} - {self.nombre}" if nombre_producto else self.nombre


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
    producto = models.ForeignKey('Producto', models.SET_NULL, blank=True, null=True)
    cantidad_movida = models.IntegerField(default=0)
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


class AjusteInventario(models.Model):
    """
    Ajuste manual de entrada o salida de stock (cabecera), para los casos
    donde un proveedor entrega una nota de entrega/albarán en vez de una
    factura, o para corregir el stock tras un conteo físico. Todo el
    documento es de un solo `tipo` (entrada o salida) -- no se mezclan
    líneas de entrada y salida en un mismo ajuste, igual que una nota de
    entrega real solo mueve mercancía en una dirección.
    """
    TIPO_CHOICES = (
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
    )
    MOTIVO_CHOICES = (
        ('compra_con_factura', 'Compra con factura fiscal'),
        ('compra_sin_factura', 'Compra con nota de entrega (sin factura)'),
        ('conteo_fisico', 'Corrección por conteo físico'),
        ('devolucion_proveedor', 'Devolución a proveedor'),
        ('merma', 'Merma / producto dañado'),
        ('otro', 'Otro'),
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    motivo = models.CharField(max_length=30, choices=MOTIVO_CHOICES, default='otro')
    almacen = models.ForeignKey(Almacen, on_delete=models.SET_NULL, blank=True, null=True)
    proveedor = models.ForeignKey("proveedores.Proveedor", on_delete=models.SET_NULL, blank=True, null=True)
    numero_documento = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Número de la nota de entrega o de la factura fiscal del proveedor, según el motivo.",
    )
    numero_control = models.CharField(
        max_length=50, blank=True, default='',
        help_text="Número de control SENIAT de la factura fiscal del proveedor (solo aplica cuando el motivo es 'Compra con factura fiscal').",
    )
    observaciones = models.TextField(blank=True, default='')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ajustes_inventario')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # Fecha del documento FÍSICO del proveedor (la nota de entrega o
    # factura), independiente de `fecha_creacion` (cuándo se cargó al
    # sistema) -- antes no existía, así que si alguien registraba HOY una
    # compra de hace dos semanas, Cuentas por Pagar la envejecía mal (la
    # trataba como "recién emitida", ver `crear_cuenta_por_pagar_desde_ajuste`).
    # Editable después de creado (ver `AjusteInventarioViewSet.partial_update`)
    # para poder corregirla sin tener que anular y rehacer el ajuste completo.
    fecha_documento = models.DateField(
        null=True, blank=True,
        help_text="Fecha del documento del proveedor (nota de entrega/factura). Vacío = se usa la fecha en que se cargó el ajuste.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'AjusteInventario'
        ordering = ['-fecha_creacion']

    def __str__(self) -> str:
        return f"Ajuste {self.get_tipo_display()} #{self.pk}"

    @property
    def fecha_efectiva(self):
        """`fecha_documento` si se cargó; si no, la fecha en que se registró el ajuste."""
        return self.fecha_documento or self.fecha_creacion.date()


class AjusteInventarioDetalle(models.Model):
    """Línea de un `AjusteInventario`: el producto/variante y la cantidad movida."""
    ajuste = models.ForeignKey(AjusteInventario, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, models.DO_NOTHING, blank=True, null=True)
    variante = models.ForeignKey(Variacionproducto, on_delete=models.CASCADE, null=True, blank=True)
    cantidad = models.PositiveIntegerField()
    # decimal_places=6 (antes 2): productos que se compran a granel o en
    # divisa con muchos decimales (ej. costo por gramo, o un costo en USD
    # con fracciones pequeñas) necesitan más precisión que 2 decimales sin
    # perder plata por redondeo en compras de gran volumen.
    costo_unitario = models.DecimalField(
        max_digits=14, decimal_places=6, blank=True, null=True,
        help_text="Costo unitario reportado en la nota de entrega/factura del proveedor (opcional).",
    )
    # Snapshot del stock del item justo después de aplicar esta línea -- queda
    # fijo aunque el stock siga moviéndose después (kardex, no cálculo en vivo).
    stock_resultante = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'AjusteInventarioDetalle'


class TrasladoInventario(models.Model):
    """
    Traslado de stock entre dos almacenes del mismo tenant -- a propósito
    NO tiene un estado "en tránsito" ni una confirmación de recepción: se
    descuenta del origen y se suma al destino en la misma operación (ver
    `apps.inventario.services.stock_service.crear_y_aplicar_traslado`), así
    que al guardarse el traslado ya está hecho, no pendiente. `PROTECT` en
    los almacenes: borrar uno con traslados históricos rompería la
    trazabilidad de a dónde fue o de dónde vino ese stock.
    """
    almacen_origen = models.ForeignKey(Almacen, on_delete=models.PROTECT, related_name='traslados_salida')
    almacen_destino = models.ForeignKey(Almacen, on_delete=models.PROTECT, related_name='traslados_entrada')
    observaciones = models.TextField(blank=True, default='')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='traslados_inventario')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'TrasladoInventario'
        ordering = ['-fecha_creacion']

    def __str__(self) -> str:
        return f"Traslado {self.almacen_origen_id} → {self.almacen_destino_id} ({self.fecha_creacion:%d/%m/%Y})"


class TrasladoInventarioDetalle(models.Model):
    """Línea de un `TrasladoInventario`: el producto y la cantidad movida entre los dos almacenes."""
    traslado = models.ForeignKey(TrasladoInventario, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    # Snapshots del stock de CADA almacén justo después de aplicar esta
    # línea -- igual que `AjusteInventarioDetalle.stock_resultante`, queda
    # fijo como registro histórico aunque el stock se siga moviendo después.
    stock_resultante_origen = models.IntegerField(blank=True, null=True)
    stock_resultante_destino = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'TrasladoInventarioDetalle'


class Transportista(models.Model):
    nombre = models.CharField(max_length=100)
    tipo_envio = models.CharField(max_length=50)
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    precio_kg_adicional = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    tiempo_entrega = models.CharField(max_length=20)
    activo = models.BooleanField(blank=True, null=True)

    class Meta:
        db_table = 'Transportista'