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
    # Banco fijo al que entra el dinero de este método (ej. "Transferencia
    # Banesco" -> banco Banesco). No es efectivo, así que un método de
    # efectivo simplemente deja esto vacío. Referencia por string
    # ('pagos.Banco') para evitar un import circular: `apps.pagos.models`
    # ya importa `Factura` desde este mismo módulo.
    banco = models.ForeignKey(
        'pagos.Banco', on_delete=models.SET_NULL, blank=True, null=True, related_name='metodos_pago',
        help_text="Banco al que se acredita este método de pago (vacío para efectivo).",
    )
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
    # Quién hizo/registró la venta -- normalmente coincide con `usuario` (el
    # que está logueado en el POS), pero un admin puede estar registrando en
    # el sistema una venta que en realidad cerró un vendedor en la calle;
    # este campo permite atribuírsela a esa persona aunque no sea quien la
    # tipeó. Si no se especifica, se asume igual a `usuario`.
    vendedor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ventas_atribuidas",
        verbose_name="Vendedor",
        help_text="Empleado que realizó la venta (puede diferir de `usuario` si otra persona la registra en el sistema).",
    )
    CONDICION_PAGO_CHOICES = (
        ('contado', 'Contado'),
        ('credito', 'Crédito'),
    )
    condicion_pago = models.CharField(
        max_length=10, choices=CONDICION_PAGO_CHOICES, default='contado', verbose_name="Condición de Pago",
    )
    cliente = models.ForeignKey("clientes.Cliente", models.DO_NOTHING, blank=True, null=True)
    # Antes, un pedido B2B solo dejaba el nombre/RIF del comprador como texto
    # libre en `comentario_pendiente` -- sin este FK era imposible consultar
    # "todo lo que compró el cliente X" para nivel de precio automático,
    # reposición predictiva o línea de crédito.
    cliente_b2b = models.ForeignKey("clientes.ClienteB2B", models.DO_NOTHING, blank=True, null=True, related_name='pedidos_b2b')
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
    # Un pedido del catálogo público (o B2B) llega en estado 'pendiente' igual
    # que una venta a crédito del POS ("pagar luego"), pero son cosas muy
    # distintas: la venta a crédito ya es una transacción confirmada que solo
    # espera el cobro, mientras que este pedido todavía puede ser RECHAZADO
    # por el admin. Sin esta bandera, `save()` no podía distinguir ambos
    # casos y le asignaba correlativo/número de control al pedido apenas
    # llegaba -- antes incluso de que el admin lo confirmara -- lo que
    # "quemaba" numeración fiscal en pedidos que podían terminar rechazados.
    pendiente_de_aprobacion = models.BooleanField(
        default=False,
        verbose_name="Pendiente de aprobación",
        help_text="True si es un pedido (catálogo/B2B) que todavía no ha sido confirmado por el admin: no debe recibir correlativo ni número de control hasta que se apruebe.",
    )

    class Meta:
        db_table = 'Factura'

    def __str__(self) -> str:
        return f"Factura {self.correlativo or f'#{self.pk}'}"

    def save(self, *args, **kwargs):
        # `registrar_libro=False`: para el guardado inicial de una factura
        # que se sabe que se va a volver a guardar de inmediato con los
        # totales ya calculados (ej. `crear_orden_desde_pedido_publico`,
        # que crea la cabecera en 0 y llama a `recalcular_y_guardar_factura`
        # a continuación) -- sin este parámetro, ese primer guardado también
        # registraba una línea en el Libro con base_imponible/iva/total en
        # cero, que el segundo guardado pisaba de inmediato: una
        # consulta+escritura completamente desperdiciada en cada pedido.
        registrar_libro = kwargs.pop('registrar_libro', True)

        # LÓGICA DE CORRELATIVO Y NÚMERO DE CONTROL (SENIAT).
        #
        # El número de factura y el número de control se generan de forma
        # atómica (SELECT ... FOR UPDATE) para evitar condiciones de carrera
        # al emitir la factura, ya sea en estado 'pagado' o 'pendiente'.
        if not self.correlativo and self.estado in ['pagado', 'pendiente'] and not self.pendiente_de_aprobacion:
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
        if not self.numero_control and self.estado in ['pagado', 'pendiente'] and not self.pendiente_de_aprobacion:
            try:
                self.numero_control = obtener_y_actualizar_numero_control()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    "No se pudo generar el número de control de la factura: %s", e
                )

        super().save(*args, **kwargs)

        # Registro en el Libro de Ventas (SENIAT) -- se hace AQUÍ, no en el
        # serializer de la API, para que quede garantizado sin importar por
        # qué camino se guardó la factura (POS, catálogo público, un admin
        # editándola a mano): antes solo se registraba al CREAR la factura
        # desde el endpoint del panel, que ocurre en estado 'borrador' --
        # antes de que exista correlativo -- así que las ventas del POS
        # quedaban en el Libro sin número de documento, y las del catálogo
        # público (que se crean por otro camino, sin pasar por ahí) no
        # quedaban registradas en absoluto. `registrar_factura_en_libro` no
        # hace nada si todavía no hay correlativo, y actualiza (no duplica)
        # la línea existente si ya la había -- es seguro llamarla en cada
        # guardado.
        if self.correlativo and registrar_libro:
            try:
                from .services.libros_service import registrar_factura_en_libro
                registrar_factura_en_libro(self)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    "No se pudo registrar la factura %s en el Libro de Ventas: %s", self.correlativo, e
                )





class Facturaelectronica(models.Model):
    """
    Registro de facturación electrónica emitida ante el proveedor fiscal del
    país del tenant.

    Producido por un ``InvoicingAdapter`` concreto (ver
    ``apps.facturacion.core.invoicing_adapter``) -- SENIAT, DIAN, SUNAT, etc.
    El modelo es intencionalmente genérico (no tiene campos propios de un
    solo país): lo específico de cada proveedor vive en ``respuesta_proveedor``.
    """
    ESTADO_CHOICES = (
        ('pendiente', 'Pendiente de envío'),
        ('enviado', 'Enviado al proveedor'),
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado'),
        ('no_soportado', 'Sin proveedor de facturación electrónica para este país'),
    )
    factura = models.OneToOneField(Factura, models.CASCADE, blank=True, null=True, related_name='factura_electronica')
    proveedor_codigo = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="Código del InvoicingAdapter que procesó el documento (ej: 'seniat', 'dian', 'sunat').",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    csv = models.CharField(max_length=50, blank=True, null=True, verbose_name="CSV / folio fiscal")
    qr_code = models.BinaryField(blank=True, null=True)
    firma_electronica = models.TextField(blank=True, null=True)
    respuesta_proveedor = models.JSONField(
        blank=True, null=True,
        help_text="Respuesta cruda del proveedor fiscal, para auditoría/depuración.",
    )
    fecha_procesado = models.DateTimeField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
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
    # PROTECT (antes CASCADE): con CASCADE, borrar una variante de producto
    # borraba en silencio la línea de factura que la vendió -- una factura
    # ya emitida perdía uno de sus renglones sin dejar rastro, lo cual es
    # justo lo que una auditoría fiscal no puede permitir. Con PROTECT, ese
    # borrado se rechaza mientras exista al menos una factura que la use.
    variante = models.ForeignKey('inventario.Variacionproducto', on_delete=models.PROTECT, null=True, blank=True)
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    subtotal_linea = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    iva_linea = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_linea = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self) -> str:
        nombre_producto = getattr(self.producto, 'nombre', None) or f"producto #{self.producto_id}"
        return f"{self.cantidad} x {nombre_producto} (Factura #{self.factura_id})"

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


class CajaSesion(models.Model):
    """
    Turno de caja de UN vendedor/cajero (no de una terminal física -- cada
    usuario abre y cierra su propio turno, sin importar en qué equipo esté
    parado). Mientras está abierto (`activo=True`), todos los pagos que ese
    usuario registra en el POS quedan enlazados a esta sesión
    (`Transaccionpago.caja_sesion`), para poder cuadrar cuánto debería haber
    de cada moneda al cerrar (ver `CajaSesionMonto`).
    """
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sesiones_caja')
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(blank=True, null=True)
    observaciones_cierre = models.TextField(blank=True, default='')
    # True mientras el turno sigue abierto. Se usa para encontrar "la sesión
    # activa de este usuario" en vez de una fecha de cierre nula -- más
    # explícito y permite, en el futuro, alguna sesión cerrada sin fecha por
    # una migración de datos sin que se confunda con una abierta.
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'CajaSesion'
        ordering = ['-fecha_apertura']

    def __str__(self) -> str:
        estado = "abierta" if self.activo else "cerrada"
        return f"Turno de {self.usuario} ({estado}, desde {self.fecha_apertura:%d/%m/%Y %H:%M})"


class CajaSesionMonto(models.Model):
    """
    Línea de apertura/cierre de UNA moneda dentro de un turno de caja. Un
    turno puede manejar varias monedas a la vez (efectivo en Bs Y en USD),
    y cada una se cuenta y cuadra por separado -- nunca se mezclan (mismo
    criterio que ya usa `obtener_cierre_caja_service`).
    """
    caja_sesion = models.ForeignKey(CajaSesion, on_delete=models.CASCADE, related_name='montos')
    moneda = models.ForeignKey('configuracion.Moneda', on_delete=models.PROTECT)
    monto_apertura = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Se calculan/llenan al cerrar el turno -- `esperado` es lo que el
    # sistema calcula que debería haber (apertura + cobros en efectivo -
    # vueltos dados), `declarado` es lo que el cajero contó físicamente.
    monto_cierre_esperado = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    monto_cierre_declarado = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)

    class Meta:
        db_table = 'CajaSesionMonto'
        unique_together = (('caja_sesion', 'moneda'),)

    @property
    def diferencia(self):
        if self.monto_cierre_esperado is None or self.monto_cierre_declarado is None:
            return None
        return self.monto_cierre_declarado - self.monto_cierre_esperado


class Transaccionpago(models.Model):
    # `orden` es un enlace heredado a un modelo legado que ya casi no se usa
    # (las ventas actuales viven en `Factura`, no en `Orden`) -- se deja para
    # no romper filas históricas, pero las transacciones nuevas se enlazan
    # por `factura`, que sí es el modelo real de la venta.
    orden = models.ForeignKey(Orden, models.DO_NOTHING, blank=True, null=True)
    factura = models.ForeignKey(
        'Factura', models.SET_NULL, blank=True, null=True, related_name='transacciones_pago',
        help_text="Factura/pedido al que corresponde este pago.",
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    # Lo que el cliente entregó de verdad -- para efectivo puede ser mayor a
    # `monto` (ej. paga con un billete más grande) y en ese caso `vuelto`
    # guarda cuánto se le devolvió. Para métodos no-efectivo, es igual a
    # `monto` (no hay vuelto en una transferencia).
    monto_recibido = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    vuelto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    metodo_pago = models.ForeignKey(MetodoPago, models.DO_NOTHING, blank=True, null=True)
    # Turno de caja del cajero que cobró -- nulo para pagos que no pasaron
    # por el POS (ej. viejos registros, o pagos confirmados desde Pedidos).
    caja_sesion = models.ForeignKey(
        CajaSesion, on_delete=models.SET_NULL, blank=True, null=True, related_name='pagos',
    )
    estado = models.CharField(max_length=20)
    codigo_transaccion = models.CharField(unique=True, max_length=100, blank=True, null=True)
    # Referencia/comprobante que el cliente o el cajero ingresan a mano (N° de
    # Pago Móvil, transferencia, Zelle, etc.) -- para que el admin pueda
    # corroborar el pago real contra lo que el sistema registró. Distinto de
    # `codigo_transaccion`, que es un UUID interno generado por el sistema.
    referencia = models.CharField(max_length=100, blank=True, null=True, verbose_name="Referencia de pago")
    fecha = models.DateTimeField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'TransaccionPago'

    def __str__(self) -> str:
        return f"Pago {self.monto} ({self.estado}) - Factura #{self.factura_id or 's/factura'}"


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
    # Consolidación en moneda base del tenant (mismo patrón que
    # `Factura.total_base` etc.) -- antes la nota solo guardaba sus montos
    # en la moneda propia de la factura asociada, así que su reporte/PDF no
    # tenía forma de mostrar el equivalente en Bs sin recalcularlo a mano.
    base_imponible_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Base Imponible (moneda base)")
    iva_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="IVA (moneda base)")
    retencion_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Retención (moneda base)")
    total_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total (moneda base)")
    activo = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        db_table = 'NotaCredito'
        verbose_name = "Nota de Crédito"
        verbose_name_plural = "Notas de Crédito"
        ordering = ['-fecha_emision']

    def __str__(self) -> str:
        return f"Nota de Crédito {self.numero_nota}"


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
    # Ver el mismo comentario en NotaCredito.
    base_imponible_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Base Imponible (moneda base)")
    iva_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="IVA (moneda base)")
    total_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total (moneda base)")
    activo = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        db_table = 'NotaDebito'
        verbose_name = "Nota de Débito"
        verbose_name_plural = "Notas de Débito"
        ordering = ['-fecha_emision']

    def __str__(self) -> str:
        return f"Nota de Débito {self.numero_nota}"


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
            # `registrar_en_libro_compra_venta` (libros_service.py) hace un
            # `update_or_create` filtrando por este par en CADA guardado de
            # factura/nota -- sin índice, ese SELECT escanea toda la tabla.
            models.Index(fields=['tipo_documento', 'numero_documento'], name='idx_libro_tipo_numero'),
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
    # Periodo fiscal que declara el PROVEEDOR en su comprobante (ej: "2026",
    # "01/2026") -- texto libre a propósito: es un dato que el cliente/
    # proveedor informa en el papel/PDF que entrega, no algo que el sistema
    # calcule, y su formato varía según cómo lo exprese cada uno.
    periodo_imposicion = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="Periodo de Imposición",
        help_text="Periodo fiscal que declara el proveedor (ej: 2026, 01/2026).",
    )
    fecha_emision = models.DateField(auto_now_add=True, verbose_name="Fecha de Emisión")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        db_table = 'Retencion'
        verbose_name = "Comprobante de Retención"
        verbose_name_plural = "Comprobantes de Retención"
        ordering = ['-fecha_emision']

    def __str__(self) -> str:
        return f"Retención {self.numero_comprobante or f'#{self.pk}'} ({self.get_tipo_retencion_display()})"
