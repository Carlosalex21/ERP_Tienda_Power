"""
CRM ligero: seguimiento comercial (`Oportunidad`, un pipeline simple de
"esto podría convertirse en venta") y cotizaciones formales (`Cotizacion`,
un presupuesto con líneas y precios que el cliente puede aceptar antes de
comprometerse a comprar) -- ninguno de los dos afecta inventario ni caja
hasta que una cotización se convierte en una venta real (ver
`apps.crm.services.convertir_cotizacion_a_venta`).
"""
import secrets

from django.conf import settings
from django.db import models, transaction


class Oportunidad(models.Model):
    """
    Una posible venta que todavía se está trabajando -- desde "until llamó
    preguntando precios" hasta "ganada" o "perdida". El cliente puede ser
    uno ya registrado o solo un prospecto (nombre/teléfono sueltos, mismo
    criterio que `Factura.nombre_cliente_pendiente` para pedidos públicos
    sin cliente formal) -- no se obliga a crear la ficha completa del
    cliente solo para anotar un posible negocio.
    """
    ETAPA_CHOICES = (
        ('nuevo', 'Nuevo'),
        ('contactado', 'Contactado'),
        ('cotizado', 'Cotizado'),
        ('negociacion', 'En negociación'),
        ('ganado', 'Ganado'),
        ('perdido', 'Perdido'),
    )
    titulo = models.CharField(max_length=200)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='oportunidades')
    nombre_prospecto = models.CharField(max_length=150, blank=True, default='')
    telefono_prospecto = models.CharField(max_length=30, blank=True, default='')
    etapa = models.CharField(max_length=15, choices=ETAPA_CHOICES, default='nuevo')
    valor_estimado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    fecha_cierre_estimada = models.DateField(null=True, blank=True)
    # Cuándo hay que volver a contactar -- el Centro de Alertas avisa solo
    # cuando esta fecha ya pasó y la oportunidad sigue abierta (ver
    # `apps.reportes.core.alertas_service`), para que un seguimiento
    # comercial no se quede frío solo porque nadie se acordó.
    proximo_seguimiento = models.DateField(null=True, blank=True)
    usuario_asignado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='oportunidades_asignadas')
    departamento = models.ForeignKey('rrhh.Departamento', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    observaciones = models.TextField(blank=True, default='')
    motivo_perdida = models.CharField(max_length=255, blank=True, default='')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Oportunidad'
        ordering = ['-fecha_creacion']
        verbose_name = 'Oportunidad'
        verbose_name_plural = 'Oportunidades'

    def __str__(self) -> str:
        return self.titulo

    @property
    def nombre_contacto(self) -> str:
        if self.cliente_id:
            return self.cliente.nombre
        return self.nombre_prospecto or 'Sin nombre'


class Cotizacion(models.Model):
    """
    Presupuesto formal con líneas y precios -- se emite en 'borrador', se
    envía, y el cliente la acepta o rechaza. Aceptarla NO es venderla: la
    venta real (con su propio descuento de stock y cobro) se crea aparte al
    convertirla (ver `apps.crm.services.convertir_cotizacion_a_venta`), así
    una cotización rechazada o vencida nunca tocó inventario ni caja.
    """
    ESTADO_CHOICES = (
        ('borrador', 'Borrador'),
        ('enviada', 'Enviada'),
        ('aceptada', 'Aceptada'),
        ('rechazada', 'Rechazada'),
        ('vencida', 'Vencida'),
        ('convertida', 'Convertida en venta'),
    )
    numero = models.CharField(max_length=20, unique=True, editable=False)
    oportunidad = models.ForeignKey(Oportunidad, on_delete=models.SET_NULL, null=True, blank=True, related_name='cotizaciones')
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='cotizaciones')
    nombre_prospecto = models.CharField(max_length=150, blank=True, default='')
    telefono_prospecto = models.CharField(max_length=30, blank=True, default='')
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default='borrador')
    moneda = models.ForeignKey('configuracion.Moneda', on_delete=models.SET_NULL, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    iva_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    fecha_emision = models.DateField(auto_now_add=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True, default='')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    # Se llena al convertirla en una venta real -- de ahí en adelante la
    # cotización queda de solo lectura (histórica).
    factura_generada = models.OneToOneField('facturacion.Factura', on_delete=models.SET_NULL, null=True, blank=True, related_name='cotizacion_origen')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # Token opaco para que el cliente pueda ver/aceptar su cotización sin
    # login -- mismo patrón que `OrdenServicio.token_publico`.
    token_publico = models.CharField(max_length=64, unique=True, editable=False, blank=True)

    class Meta:
        db_table = 'Cotizacion'
        ordering = ['-fecha_creacion']
        verbose_name = 'Cotización'
        verbose_name_plural = 'Cotizaciones'

    def __str__(self) -> str:
        return f'COT-{self.numero}'

    def save(self, *args, **kwargs):
        if not self.token_publico:
            self.token_publico = secrets.token_urlsafe(24)
        if not self.numero:
            with transaction.atomic():
                ultimo = Cotizacion.objects.select_for_update().order_by('-id').first()
                siguiente = (int(ultimo.numero) + 1) if (ultimo and ultimo.numero.isdigit()) else 1
                self.numero = str(siguiente).zfill(5)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @property
    def nombre_contacto(self) -> str:
        if self.cliente_id:
            return self.cliente.nombre
        return self.nombre_prospecto or 'Sin nombre'


class CotizacionDetalle(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT)
    variante = models.ForeignKey('inventario.Variacionproducto', on_delete=models.PROTECT, null=True, blank=True)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'CotizacionDetalle'

    def __str__(self) -> str:
        return f'{self.cantidad} x {self.producto.nombre}'

    @property
    def subtotal_linea(self):
        return self.precio_unitario * self.cantidad
