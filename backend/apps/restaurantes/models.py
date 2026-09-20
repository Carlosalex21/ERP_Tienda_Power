import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models


class Mesa(models.Model):
    """Mesa física del restaurante/bar (o "Barra 1", "Terraza 3", etc.)."""

    numero = models.CharField(max_length=20, unique=True, verbose_name="Número/Nombre")
    capacidad = models.PositiveIntegerField(blank=True, null=True, help_text="Cantidad de comensales que caben.")
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Mesa'
        ordering = ['numero']

    def __str__(self) -> str:
        return self.numero

    @property
    def pedido_abierto(self):
        return self.pedidos.filter(estado='abierto').first()


class PedidoMesa(models.Model):
    """
    Pedido en curso de una mesa: se le van agregando ítems mientras los
    comensales piden, y se factura de una sola vez al cerrar -- separado de
    `Factura` a propósito, para que agregar/quitar un plato mientras la
    mesa sigue abierta no toque numeración fiscal ni cálculos de IVA hasta
    que de verdad se cobra (ver `apps.restaurantes.services.cerrar_pedido_mesa`).
    """

    ESTADO_CHOICES = (
        ('abierto', 'Abierto'),
        ('cerrado', 'Cerrado'),
    )

    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name='pedidos')
    mesero = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedidos_mesa_atendidos',
    )
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierto')
    # Se llena recién al cerrar el pedido (ver `cerrar_pedido_mesa`) -- un
    # pedido abierto todavía no es una venta fiscal.
    factura = models.OneToOneField(
        'facturacion.Factura', on_delete=models.SET_NULL, null=True, blank=True, related_name='pedido_mesa',
    )
    # Token opaco (no correlativo, no adivinable) para el acceso público de
    # "dividir cuenta" vía QR -- cualquiera con el link ve el pedido de ESTA
    # mesa nada más, sin login. Se regenera en cada pedido nuevo, así un QR
    # viejo pegado en la mesa deja de servir apenas se abre la cuenta
    # siguiente.
    token_publico = models.CharField(max_length=64, unique=True, editable=False)
    # Estado compartido de la división de cuenta -- lo puede tocar cualquiera
    # que escanee el QR (ver `apps.restaurantes.api.views_publica`), así que
    # vive en el pedido, no por-persona: todos los que escanean ven y ajustan
    # el MISMO valor, como billete físico pasando de mano en mano.
    division_personas = models.PositiveIntegerField(default=1)
    propina_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    mesero_solicitado = models.BooleanField(default=False, help_text="Alguien tocó \"Llamar al mesero\" desde el QR.")
    cuenta_solicitada = models.BooleanField(default=False, help_text="Alguien tocó \"Pedir la cuenta\" desde el QR.")
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'PedidoMesa'
        ordering = ['-fecha_apertura']

    def __str__(self) -> str:
        return f"Pedido {self.mesa.numero} ({self.get_estado_display()})"

    def save(self, *args, **kwargs):
        if not self.token_publico:
            self.token_publico = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)


class PedidoMesaItem(models.Model):
    """Línea de un `PedidoMesa` -- un plato/bebida agregado a la cuenta de la mesa."""

    pedido = models.ForeignKey(PedidoMesa, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    # Snapshot del precio al agregarlo -- si el precio del producto cambia
    # mientras la mesa sigue abierta, no debe alterar lo que ya se pidió.
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    notas = models.CharField(max_length=255, blank=True, null=True, help_text='Ej. "sin cebolla", "término medio".')
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'PedidoMesaItem'
        ordering = ['creado']

    def __str__(self) -> str:
        return f"{self.cantidad} x {self.producto.nombre}"

    @property
    def subtotal(self) -> Decimal:
        return self.precio_unitario * self.cantidad
