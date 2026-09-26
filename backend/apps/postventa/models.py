from django.conf import settings
from django.db import models
from django.utils import timezone


class Garantia(models.Model):
    """
    Garantía de UNA línea vendida (`Detallefactura`) -- se genera sola al
    pagarse una factura cuyo producto tiene `Producto.meses_garantia`
    asignado (ver `apps.postventa.services.generar_garantias_de_factura`,
    llamado desde el mismo punto donde ya se dispara el resto de
    automatizaciones de una venta pagada).

    No guarda un `estado` propio -- "vigente"/"vencida" se calcula siempre
    comparando `fecha_vencimiento` contra hoy (ver `esta_vigente`), así que
    nunca puede quedar desincronizada por falta de un job que la actualice.
    """
    detalle_factura = models.OneToOneField(
        'facturacion.Detallefactura', on_delete=models.CASCADE, related_name='garantia',
    )
    factura = models.ForeignKey('facturacion.Factura', on_delete=models.CASCADE, related_name='garantias')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.SET_NULL, null=True, related_name='+')
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='garantias')
    fecha_inicio = models.DateField()
    fecha_vencimiento = models.DateField()
    meses_garantia = models.PositiveIntegerField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Garantia'
        ordering = ['-fecha_inicio']
        verbose_name = 'Garantía'
        verbose_name_plural = 'Garantías'

    def __str__(self) -> str:
        nombre_producto = getattr(self.producto, 'nombre', None) or 'producto'
        return f'Garantía {nombre_producto} - Factura #{self.factura_id}'

    @property
    def esta_vigente(self) -> bool:
        return self.fecha_vencimiento >= timezone.localdate()


class ReclamoPostventa(models.Model):
    """
    Ticket de soporte/reclamo postventa -- no depende de que exista una
    `Garantia` (un cliente puede reclamar por un producto sin garantía
    rastreada, o por un tema de servicio sin producto asociado), pero si
    viene de una venta con garantía activa se puede enlazar para que el
    encargado vea de un vistazo si sigue vigente.
    """
    ESTADO_CHOICES = (
        ('abierto', 'Abierto'),
        ('en_proceso', 'En Proceso'),
        ('resuelto', 'Resuelto'),
        ('rechazado', 'Rechazado'),
    )
    PRIORIDAD_CHOICES = (
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
    )
    garantia = models.ForeignKey(Garantia, on_delete=models.SET_NULL, null=True, blank=True, related_name='reclamos')
    factura = models.ForeignKey('facturacion.Factura', on_delete=models.SET_NULL, null=True, blank=True, related_name='reclamos_postventa')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='reclamos_postventa')
    # Mismo respaldo que `apps.crm.Oportunidad.nombre_prospecto` -- un
    # reclamo puede venir de alguien sin `Cliente` registrado (ej. un
    # comprador del catálogo público que nunca creó cuenta).
    nombre_contacto_libre = models.CharField(max_length=150, blank=True, default='')
    telefono_contacto = models.CharField(max_length=30, blank=True, default='')

    titulo = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, default='')
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='abierto')
    prioridad = models.CharField(max_length=10, choices=PRIORIDAD_CHOICES, default='media')
    usuario_asignado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    resolucion = models.TextField(blank=True, default='')
    usuario_creador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ReclamoPostventa'
        ordering = ['-fecha_apertura']
        verbose_name = 'Reclamo Postventa'
        verbose_name_plural = 'Reclamos Postventa'

    def __str__(self) -> str:
        return f'Reclamo #{self.id}: {self.titulo}'

    @property
    def nombre_contacto(self) -> str:
        if self.cliente_id:
            return self.cliente.nombre
        return self.nombre_contacto_libre or 'Sin identificar'
