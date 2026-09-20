import secrets

from django.conf import settings
from django.db import models, transaction


class OrdenServicio(models.Model):
    """Orden de un taller/servicio técnico -- un equipo que entra, se repara/atiende y se entrega."""

    ESTADO_CHOICES = (
        ('recibido', 'Recibido'),
        ('en_proceso', 'En Proceso'),
        ('listo', 'Listo para Entregar'),
        ('entregado', 'Entregado'),
        ('cancelado', 'Cancelado'),
    )

    # Correlativo simple propio de esta app -- no comparte numeración con
    # `ConfiguracionCorrelativo` (esa es la numeración FISCAL de facturas;
    # una orden de servicio recién recibida todavía no es una venta).
    numero = models.CharField(max_length=20, unique=True, editable=False)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, related_name='ordenes_servicio')
    equipo = models.CharField(max_length=255, verbose_name="Equipo/artículo", help_text='Ej. "Laptop HP Pavilion", "Nevera Whirlpool".')
    descripcion_falla = models.TextField(blank=True, null=True)
    diagnostico = models.TextField(blank=True, null=True)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='recibido')
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordenes_servicio_asignadas',
    )
    costo_estimado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Se llena recién al cerrar/cobrar la orden (ver `apps.servicios.services.cerrar_orden_servicio`).
    factura = models.OneToOneField(
        'facturacion.Factura', on_delete=models.SET_NULL, null=True, blank=True, related_name='orden_servicio',
    )
    fecha_recepcion = models.DateTimeField(auto_now_add=True)
    fecha_entrega_estimada = models.DateField(blank=True, null=True)
    fecha_entrega_real = models.DateTimeField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    # Token opaco para que el cliente pueda ver el estado de su orden sin
    # login (mismo patrón que `PedidoMesa.token_publico`) -- se genera solo
    # una vez, al crear la orden.
    token_publico = models.CharField(max_length=64, unique=True, editable=False, blank=True)

    class Meta:
        db_table = 'OrdenServicio'
        ordering = ['-fecha_recepcion']

    def __str__(self) -> str:
        return f"OS-{self.numero} -- {self.equipo}"

    def save(self, *args, **kwargs):
        if not self.token_publico:
            self.token_publico = secrets.token_urlsafe(24)
        if not self.numero:
            # `select_for_update` sobre la última fila -- evita que dos
            # órdenes creadas casi al mismo tiempo saquen el mismo número
            # (misma idea que `obtener_y_actualizar_correlativo` para
            # facturas, ver `apps.configuracion.core.config_service`).
            with transaction.atomic():
                ultimo = OrdenServicio.objects.select_for_update().order_by('-id').first()
                siguiente = (int(ultimo.numero) + 1) if (ultimo and ultimo.numero.isdigit()) else 1
                self.numero = str(siguiente).zfill(5)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)
