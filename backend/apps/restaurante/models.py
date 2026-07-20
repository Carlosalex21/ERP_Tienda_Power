import uuid
from django.db import models
from django.conf import settings

# Modelos de otras apps que necesitaremos
from apps.inventario.models import Producto, Variacionproducto
from apps.facturacion.models import MetodoPago

class Mesa(models.Model):
    """
    Representa una mesa física en el restaurante de un tenant.
    Cada mesa tendrá un QR único asociado a su ID.
    """
    tenant = models.ForeignKey(settings.TENANT_MODEL, on_delete=models.CASCADE, related_name="mesas")
    nombre = models.CharField(max_length=100, help_text="Ej: 'Mesa 5', 'Barra Izquierda'")
    numero = models.PositiveIntegerField()
    qr_code_identifier = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        unique_together = ('tenant', 'numero') # No puede haber dos mesas con el mismo número en un mismo tenant
        ordering = ['numero']

    def __str__(self):
        return f"{self.nombre} (Tenant: {self.tenant.schema_name})"

class MesaSession(models.Model):
    """
    Gestiona una sesión de pedido activa en una mesa.
    Una mesa solo puede tener una sesión 'abierta' a la vez.
    """
    class EstadoSesion(models.TextChoices):
        ABIERTA = 'abierta', 'Abierta'
        CERRANDO = 'cerrando', 'Cerrando (Pagos en proceso)'
        PAGADA = 'pagada', 'Pagada'
        CANCELADA = 'cancelada', 'Cancelada'

    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="sesiones")
    session_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, help_text="ID público para la URL y WebSockets")
    estado = models.CharField(max_length=20, choices=EstadoSesion.choices, default=EstadoSesion.ABIERTA)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Sesión {self.session_uuid} en {self.mesa.nombre}"

class MesaParticipante(models.Model):
    """
    Un participante (comensal) dentro de una sesión de mesa.
    Puede ser un usuario autenticado o un invitado temporal.
    """
    sesion = models.ForeignKey(MesaSession, on_delete=models.CASCADE, related_name="participantes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    nombre_temporal = models.CharField(max_length=50, help_text="Nombre para invitados no registrados")
    es_host = models.BooleanField(default=False)
    fecha_union = models.DateTimeField(auto_now_add=True)

    def get_nombre(self):
        return self.usuario.get_full_name() if self.usuario else self.nombre_temporal

    def __str__(self):
        return f"{self.get_nombre()} en sesión {self.sesion.session_uuid}"

class ItemPedidoMesa(models.Model):
    """
    Un ítem específico pedido por un participante en una sesión.
    Esta es la unidad atómica para el cálculo de la cuenta individual.
    """
    class EstadoCocina(models.TextChoices):
        RECIBIDO = 'recibido', 'Recibido'
        PREPARANDO = 'preparando', 'En preparación'
        LISTO = 'listo_para_servir', 'Listo para servir'
        SERVIDO = 'servido', 'Servido'

    sesion = models.ForeignKey(MesaSession, on_delete=models.CASCADE, related_name="items_pedidos")
    participante = models.ForeignKey(MesaParticipante, on_delete=models.PROTECT, related_name="items_pedidos")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    variante = models.ForeignKey(Variacionproducto, null=True, blank=True, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario_congelado = models.DecimalField(max_digits=10, decimal_places=2, help_text="Precio al momento de pedir")
    estado_cocina = models.CharField(max_length=20, choices=EstadoCocina.choices, default=EstadoCocina.RECIBIDO)
    pagado = models.BooleanField(default=False, help_text="Marca si este ítem específico ya fue cubierto por un pago")

    @property
    def total_linea(self):
        return self.cantidad * self.precio_unitario_congelado

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre} para {self.participante.get_nombre()}"

class PagoMesa(models.Model):
    """
    Registra cada transacción de pago realizada contra una sesión.
    Esencial para conciliar pagos parciales y cerrar la sesión.
    """
    sesion = models.ForeignKey(MesaSession, on_delete=models.CASCADE, related_name="pagos")
    participante = models.ForeignKey(MesaParticipante, null=True, on_delete=models.SET_NULL, help_text="Quién realizó el pago")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT)
    referencia_pago = models.CharField(max_length=255, blank=True, help_text="Ej: Referencia de PagoMóvil, ID de Stripe")
    fecha_pago = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pago de {self.monto} en sesión {self.sesion.session_uuid}"
