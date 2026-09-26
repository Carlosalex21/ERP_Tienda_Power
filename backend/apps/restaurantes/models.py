import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property


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

    @cached_property
    def pedido_abierto(self):
        # `cached_property` (no `@property`) a propósito: `MesaSerializer` lo
        # consulta varias veces por instancia (estado, pedido_abierto_id,
        # mesero_solicitado, cuenta_solicitada) -- sin cachear, cada acceso
        # repetía la misma query por cada mesa de la grilla.
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
    # Datos de pago de quien va a cobrarle al resto del grupo (banco, titular,
    # teléfono/cédula para Pago Móvil, etc.) -- texto libre a propósito: cada
    # país/método tiene sus propios campos y no vale la pena modelarlos todos.
    # Igual que `propina_pct`/`division_personas`, es compartido: quien lo
    # llena lo ve todo el grupo en la misma página (no hay login individual
    # por comensal), así los demás solo copian y pegan al transferir.
    datos_pago_anfitrion = models.TextField(blank=True, default='')
    # PIN de 4 dígitos que protege `datos_pago_anfitrion` -- sin esto,
    # cualquiera con el link del QR (todo el grupo) podía sobreescribir los
    # datos bancarios de otra persona por error o a propósito. Se genera al
    # guardarlos por primera vez; para cambiarlos después hace falta el
    # mismo PIN (ver `ActualizarDivisionSerializer`/`PedidoMesaPublicoView.patch`).
    pin_anfitrion = models.CharField(max_length=4, blank=True, default='')
    # Foto/captura del comprobante de transferencia -- la sube quien ya
    # pagó, para que el anfitrión (o el mesero) confirme visualmente sin
    # depender de que alguien avise por fuera del sistema.
    comprobante_pago = models.ImageField(upload_to='comprobantes_pago_mesa/', blank=True, null=True)
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
    # ¿A cuál de las N personas que dividen la cuenta corresponde este ítem?
    # 1..división_personas, o `None` si es compartido entre todo el grupo
    # (se reparte por igual entre todos al calcular cada porción -- ver
    # `apps.restaurantes.services.calcular_division_por_persona`).
    persona_asignada = models.PositiveIntegerField(null=True, blank=True)
    # Para la vista de cocina (`/admin/restaurante/cocina`) -- separado de
    # `estado` del pedido (que es sobre la CUENTA, no sobre cada plato):
    # un pedido puede seguir abierto mucho después de que todo ya se sirvió.
    preparado = models.BooleanField(default=False)
    # Snapshot de `producto.departamento` al agregar el ítem (ver
    # `PedidoMesaViewSet.agregar_item`) -- permite que la vista de cocina se
    # filtre por estación ("Cocina", "Barra"...) en vez de mostrarle a TODO
    # el personal TODOS los platos de TODAS las mesas.
    departamento = models.ForeignKey(
        'rrhh.Departamento', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    preparado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    fecha_preparado = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'PedidoMesaItem'
        ordering = ['creado']

    def __str__(self) -> str:
        return f"{self.cantidad} x {self.producto.nombre}"

    @property
    def subtotal(self) -> Decimal:
        return self.precio_unitario * self.cantidad


class PushSubscription(models.Model):
    """
    Suscripción de Web Push de un usuario de staff -- para avisarle "llaman
    al mesero"/"piden la cuenta" aunque no tenga la pestaña del panel
    abierta o el teléfono tenga la pantalla apagada (el WebSocket de
    `apps.restaurantes.consumers` solo funciona con la conexión activa).
    Un mismo usuario puede tener varias (un navegador/dispositivo cada una).
    """
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'PushSubscription'

    def __str__(self) -> str:
        return f"Push de {self.usuario} ({self.endpoint[:40]}...)"
