"""
Inmuebles: administración de condominios e inmobiliaria sobre un mismo motor.

- **Estructura:** `Edificio` -> `Unidad` (apartamento, casa, local...). Una unidad
  sin edificio es una propiedad suelta de una inmobiliaria.
- **Cobranza (compartida):** `Cargo` (lo que se debe) <- `ReciboAplicacion` ->
  `Recibo` (lo que se pagó). Todo se guarda en USD; el pago guarda la tasa usada.
- **Condominios:** `GastoComun` + `PeriodoCondominio` (distribución por alícuota).
- **Inmobiliaria:** `Contrato` de arrendamiento, `GastoPropiedad` y
  `Liquidacion` al propietario.
- **Portal:** `PortalAcceso` (enlace secreto por persona) y `PagoReportado`
  (el condómino/inquilino avisa su pago; la administradora lo aprueba).
"""
import os
import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction

PERIODO_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


def validar_periodo(valor: str) -> None:
    if not PERIODO_RE.match(valor or ''):
        raise ValidationError('El período debe tener el formato AAAA-MM (ej. 2026-10).')


def _ruta_privada(carpeta: str, filename: str) -> str:
    # Nombre aleatorio e impredecible: los archivos se sirven desde /media/ sin
    # autenticación, así que la única protección de un comprobante o contrato es
    # que nadie pueda adivinar su ruta.
    extension = os.path.splitext(filename or '')[1].lower()
    return f'inmuebles/{carpeta}/{uuid.uuid4().hex}{extension}'


def ruta_comprobantes(instance, filename):
    return _ruta_privada('comprobantes', filename)


def ruta_fotos(instance, filename):
    return _ruta_privada('fotos', filename)


def ruta_contratos(instance, filename):
    return _ruta_privada('contratos', filename)


def ruta_gastos(instance, filename):
    return _ruta_privada('gastos', filename)


class Monto(models.DecimalField):
    """Dinero en USD con 2 decimales."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_digits', 14)
        kwargs.setdefault('decimal_places', 2)
        super().__init__(*args, **kwargs)


# --- Estructura ---------------------------------------------------------------

class Edificio(models.Model):
    """Condominio, conjunto residencial o edificio administrado."""
    nombre = models.CharField(max_length=150)
    direccion = models.TextField(blank=True, default='')
    rif = models.CharField(max_length=20, blank=True, default='')
    dia_vencimiento = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(28)],
        help_text='Día del mes en que vencen las cuotas (por defecto al emitir un período).',
    )
    mora_pct_mensual = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='% mensual de mora sobre el saldo vencido (0 = no cobra mora).',
    )
    dias_gracia = models.PositiveSmallIntegerField(default=0, help_text='Días después del vencimiento antes de aplicar mora.')
    fondo_reserva_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='% que se suma a los gastos comunes como fondo de reserva.',
    )
    portal_muestra_morosidad = models.BooleanField(
        default=False,
        help_text='Si está activo, el portal de cada condómino muestra el resumen de morosidad del edificio (solo códigos de unidad, sin nombres).',
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self) -> str:
        return self.nombre


class Unidad(models.Model):
    """Apartamento, casa, local... de un edificio, o propiedad suelta de una inmobiliaria."""
    TIPO_CHOICES = (
        ('apartamento', 'Apartamento'), ('casa', 'Casa'), ('townhouse', 'Townhouse'),
        ('local', 'Local comercial'), ('oficina', 'Oficina'), ('galpon', 'Galpón'),
        ('terreno', 'Terreno'), ('estacionamiento', 'Estacionamiento'), ('deposito', 'Depósito'),
        ('otro', 'Otro'),
    )
    ESTADO_CHOICES = (
        ('ocupada', 'Ocupada'), ('disponible', 'Disponible'), ('mantenimiento', 'En mantenimiento'),
    )
    OPERACION_CHOICES = (
        ('ninguna', 'No se ofrece'), ('alquiler', 'Alquiler'), ('venta', 'Venta'), ('alquiler_venta', 'Alquiler o venta'),
    )

    edificio = models.ForeignKey(Edificio, on_delete=models.PROTECT, null=True, blank=True, related_name='unidades')
    codigo = models.CharField(max_length=40, help_text='Ej. "Apto 3-B", "Casa 12", "Local 4".')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='apartamento')
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='ocupada')
    alicuota = models.DecimalField(
        max_digits=7, decimal_places=4, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='% de participación en los gastos comunes (las de un edificio deben sumar 100).',
    )
    area_m2 = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    propietario = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='unidades_propias')
    ocupante = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='unidades_ocupadas')

    # Datos comerciales (inmobiliaria)
    operacion = models.CharField(max_length=15, choices=OPERACION_CHOICES, default='ninguna')
    publicada = models.BooleanField(default=False, help_text='Aparece en el portal público de propiedades.')
    titulo = models.CharField(max_length=160, blank=True, default='')
    descripcion = models.TextField(blank=True, default='')
    direccion = models.CharField(max_length=255, blank=True, default='')
    zona = models.CharField(max_length=120, blank=True, default='', help_text='Urbanización, sector o zona.')
    ciudad = models.CharField(max_length=80, blank=True, default='')
    precio_venta_usd = Monto(null=True, blank=True)
    canon_usd = Monto(null=True, blank=True, help_text='Canon de alquiler mensual sugerido.')
    habitaciones = models.PositiveSmallIntegerField(null=True, blank=True)
    banos = models.PositiveSmallIntegerField(null=True, blank=True)
    estacionamientos = models.PositiveSmallIntegerField(null=True, blank=True)
    area_construida_m2 = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    amenidades = ArrayField(models.CharField(max_length=40), default=list, blank=True)

    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['edificio__nombre', 'codigo']
        constraints = [
            models.UniqueConstraint(fields=['edificio', 'codigo'], condition=models.Q(edificio__isnull=False), name='uniq_unidad_edificio_codigo'),
            models.UniqueConstraint(fields=['codigo'], condition=models.Q(edificio__isnull=True), name='uniq_unidad_suelta_codigo'),
        ]

    def __str__(self) -> str:
        return f'{self.edificio.nombre} · {self.codigo}' if self.edificio_id else self.codigo

    @property
    def responsable_pago(self):
        """Quien paga la cuota/canon: el ocupante en un alquiler, el propietario en un condominio."""
        return self.propietario or self.ocupante


class UnidadFoto(models.Model):
    unidad = models.ForeignKey(Unidad, on_delete=models.CASCADE, related_name='fotos')
    imagen = models.ImageField(upload_to=ruta_fotos)
    orden = models.PositiveSmallIntegerField(default=0)
    es_portada = models.BooleanField(default=False)

    class Meta:
        ordering = ['-es_portada', 'orden', 'id']


# --- Medios de cobro ----------------------------------------------------------

class MedioPago(models.Model):
    """Datos para que paguen: cuenta del edificio (o de la administradora si `edificio` es nulo)."""
    TIPO_CHOICES = (
        ('transferencia', 'Transferencia bancaria'), ('pago_movil', 'Pago móvil'), ('zelle', 'Zelle'),
        ('efectivo', 'Efectivo'), ('deposito', 'Depósito'), ('otro', 'Otro'),
    )
    edificio = models.ForeignKey(Edificio, on_delete=models.CASCADE, null=True, blank=True, related_name='medios_pago',
                                 help_text='Vacío = aplica a todas las unidades (cuenta de la administradora).')
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    titular = models.CharField(max_length=150, blank=True, default='')
    documento_titular = models.CharField(max_length=30, blank=True, default='', help_text='RIF o cédula del titular.')
    banco = models.CharField(max_length=100, blank=True, default='')
    numero_cuenta = models.CharField(max_length=40, blank=True, default='', help_text='Cuenta, teléfono o correo según el tipo.')
    moneda = models.CharField(max_length=3, default='VES')
    instrucciones = models.TextField(blank=True, default='')
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['edificio__nombre', 'tipo', 'banco']


# --- Condominios --------------------------------------------------------------

class GastoComun(models.Model):
    CATEGORIA_CHOICES = (
        ('agua', 'Agua'), ('electricidad', 'Electricidad áreas comunes'), ('aseo', 'Aseo y limpieza'),
        ('vigilancia', 'Vigilancia'), ('mantenimiento', 'Mantenimiento y reparaciones'),
        ('ascensor', 'Ascensor'), ('jardineria', 'Jardinería'), ('administracion', 'Administración'),
        ('seguros', 'Seguros'), ('legales', 'Honorarios legales'), ('otros', 'Otros'),
    )
    edificio = models.ForeignKey(Edificio, on_delete=models.PROTECT, related_name='gastos')
    periodo = models.CharField(max_length=7, validators=[validar_periodo], help_text='Mes al que se carga el gasto (AAAA-MM).')
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='otros')
    descripcion = models.CharField(max_length=255)
    monto_usd = Monto(validators=[MinValueValidator(Decimal('0.01'))])
    proveedor = models.ForeignKey('proveedores.Proveedor', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha = models.DateField()
    comprobante = models.FileField(upload_to=ruta_gastos, null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-periodo', '-fecha', '-id']


class PeriodoCondominio(models.Model):
    """Un mes de un edificio: al emitirlo, cada unidad recibe su cuota según su alícuota."""
    ESTADO_CHOICES = (('emitido', 'Emitido'), ('anulado', 'Anulado'))
    edificio = models.ForeignKey(Edificio, on_delete=models.PROTECT, related_name='periodos')
    periodo = models.CharField(max_length=7, validators=[validar_periodo])
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='emitido')
    total_gastos_usd = Monto()
    fondo_reserva_usd = Monto(default=0)
    total_distribuido_usd = Monto()
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    emitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-periodo', 'edificio__nombre']
        constraints = [
            models.UniqueConstraint(fields=['edificio', 'periodo'], condition=~models.Q(estado='anulado'), name='uniq_periodo_edificio_vigente'),
        ]

    def __str__(self) -> str:
        return f'{self.edificio} {self.periodo}'


# --- Inmobiliaria -------------------------------------------------------------

class Contrato(models.Model):
    """Contrato de arrendamiento de una unidad."""
    ESTADO_CHOICES = (
        ('borrador', 'Borrador'), ('vigente', 'Vigente'), ('vencido', 'Vencido'), ('rescindido', 'Rescindido'),
    )
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name='contratos')
    inquilino = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, related_name='contratos_como_inquilino')
    propietario = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, null=True, blank=True, related_name='contratos_como_propietario',
                                    help_text='Se copia de la unidad al crear el contrato.')
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default='borrador')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    canon_usd = Monto(validators=[MinValueValidator(Decimal('0.01'))])
    dia_pago = models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(28)])
    deposito_usd = Monto(default=0)
    honorario_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='% que cobra la administradora sobre el canon cobrado.',
    )
    ajuste_anual_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Aumento del canon cada año de contrato.',
    )
    mora_pct_mensual = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    dias_gracia = models.PositiveSmallIntegerField(default=0)
    documento = models.FileField(upload_to=ruta_contratos, null=True, blank=True)
    contrato_anterior = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='renovaciones')
    observaciones = models.TextField(blank=True, default='')
    fecha_rescision = models.DateField(null=True, blank=True)
    motivo_rescision = models.CharField(max_length=255, blank=True, default='')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_inicio', '-id']

    def __str__(self) -> str:
        return f'Contrato {self.pk} · {self.unidad}'


class Liquidacion(models.Model):
    """Rendición de cuentas al propietario de lo cobrado en sus alquileres."""
    ESTADO_CHOICES = (('borrador', 'Borrador'), ('pagada', 'Pagada'), ('anulada', 'Anulada'))
    propietario = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, related_name='liquidaciones')
    periodo = models.CharField(max_length=7, validators=[validar_periodo], help_text='Mes en que se emite la liquidación.')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='borrador')
    total_cobrado_usd = Monto(default=0)
    honorario_usd = Monto(default=0)
    gastos_usd = Monto(default=0)
    neto_usd = Monto(default=0)
    fecha_pago = models.DateField(null=True, blank=True)
    referencia_pago = models.CharField(max_length=100, blank=True, default='')
    observaciones = models.TextField(blank=True, default='')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-periodo', '-id']


class GastoPropiedad(models.Model):
    """Reparación o mantenimiento de una propiedad que se descuenta al propietario en su liquidación."""
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name='gastos_propiedad')
    fecha = models.DateField()
    descripcion = models.CharField(max_length=255)
    monto_usd = Monto(validators=[MinValueValidator(Decimal('0.01'))])
    proveedor = models.ForeignKey('proveedores.Proveedor', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    comprobante = models.FileField(upload_to=ruta_gastos, null=True, blank=True)
    liquidacion = models.ForeignKey(Liquidacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='gastos')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-id']


# --- Cobranza -----------------------------------------------------------------

class Cargo(models.Model):
    """Una deuda de una unidad (cuota, canon, mora...). El saldo = monto - pagado."""
    TIPO_CHOICES = (
        ('cuota_condominio', 'Cuota de condominio'), ('canon', 'Canon de alquiler'),
        ('extraordinaria', 'Cuota extraordinaria'), ('multa', 'Multa'), ('mora', 'Mora'),
        ('deposito', 'Depósito en garantía'), ('otro', 'Otro'),
    )
    ESTADO_CHOICES = (('pendiente', 'Pendiente'), ('pagado', 'Pagado'), ('anulado', 'Anulado'))

    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name='cargos')
    pagador = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='cargos')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    concepto = models.CharField(max_length=200)
    periodo = models.CharField(max_length=7, validators=[validar_periodo])
    monto_usd = Monto(validators=[MinValueValidator(Decimal('0.01'))])
    monto_fondo_usd = Monto(default=0, help_text='Parte de la cuota que corresponde al fondo de reserva (informativo).')
    monto_pagado_usd = Monto(default=0)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pendiente')
    periodo_condominio = models.ForeignKey(PeriodoCondominio, on_delete=models.PROTECT, null=True, blank=True, related_name='cargos')
    contrato = models.ForeignKey(Contrato, on_delete=models.PROTECT, null=True, blank=True, related_name='cargos')
    cargo_origen = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='moras',
                                     help_text='Para una mora: la deuda que la originó.')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['fecha_vencimiento', 'id']
        indexes = [
            models.Index(fields=['estado', 'fecha_vencimiento'], name='idx_cargo_estado_venc'),
            models.Index(fields=['unidad', 'estado'], name='idx_cargo_unidad_estado'),
        ]
        constraints = [
            # Generar dos veces el mismo período/mes/mora nunca duplica una deuda.
            models.UniqueConstraint(fields=['periodo_condominio', 'unidad'], condition=models.Q(periodo_condominio__isnull=False) & ~models.Q(estado='anulado'), name='uniq_cargo_periodo_unidad'),
            models.UniqueConstraint(fields=['contrato', 'periodo', 'tipo'], condition=models.Q(contrato__isnull=False) & models.Q(tipo='canon') & ~models.Q(estado='anulado'), name='uniq_cargo_canon_contrato_periodo'),
            models.UniqueConstraint(fields=['cargo_origen', 'periodo'], condition=models.Q(tipo='mora') & ~models.Q(estado='anulado'), name='uniq_cargo_mora_origen_periodo'),
        ]

    def __str__(self) -> str:
        return f'{self.concepto} · {self.unidad}'

    @property
    def saldo_usd(self) -> Decimal:
        if self.estado == 'anulado':
            return Decimal('0.00')
        return (self.monto_usd or 0) - (self.monto_pagado_usd or 0)


class Recibo(models.Model):
    """Un pago recibido. Puede saldar varios cargos; lo que sobre queda como crédito."""
    METODO_CHOICES = MedioPago.TIPO_CHOICES
    ESTADO_CHOICES = (('confirmado', 'Confirmado'), ('anulado', 'Anulado'))

    numero = models.CharField(max_length=20, unique=True, editable=False)
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name='recibos')
    pagador = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='recibos')
    fecha = models.DateField()
    metodo = models.CharField(max_length=15, choices=METODO_CHOICES, default='transferencia')
    referencia = models.CharField(max_length=100, blank=True, default='')
    banco = models.CharField(max_length=100, blank=True, default='')
    moneda_pago = models.CharField(max_length=3, default='USD')
    monto_pago = models.DecimalField(max_digits=16, decimal_places=2, help_text='Monto recibido, en la moneda en que se pagó.')
    tasa = models.DecimalField(max_digits=16, decimal_places=6, default=1, help_text='Unidades de moneda base por 1 USD al momento del pago.')
    monto_usd = Monto()
    monto_disponible_usd = Monto(default=0, help_text='Parte del pago que no se aplicó a ninguna deuda (saldo a favor).')
    comprobante = models.FileField(upload_to=ruta_comprobantes, null=True, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default='confirmado')
    observaciones = models.TextField(blank=True, default='')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_anulacion = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-fecha', '-id']

    def __str__(self) -> str:
        return self.numero

    def save(self, *args, **kwargs):
        if not self.numero:
            # Correlativo propio (REC-000001), bloqueando la última fila para que
            # dos pagos casi simultáneos no obtengan el mismo número.
            with transaction.atomic():
                ultimo = Recibo.objects.select_for_update().order_by('-id').first()
                siguiente = (int(ultimo.numero.split('-')[-1]) + 1) if (ultimo and ultimo.numero.split('-')[-1].isdigit()) else 1
                self.numero = f'REC-{siguiente:06d}'
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


class ReciboAplicacion(models.Model):
    recibo = models.ForeignKey(Recibo, on_delete=models.CASCADE, related_name='aplicaciones')
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name='aplicaciones')
    monto_usd = Monto(validators=[MinValueValidator(Decimal('0.01'))])
    liquidacion = models.ForeignKey(Liquidacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='aplicaciones',
                                    help_text='Liquidación al propietario en la que ya se incluyó este cobro.')

    class Meta:
        ordering = ['id']


class LiquidacionLinea(models.Model):
    TIPO_CHOICES = (('canon', 'Canon cobrado'), ('honorario', 'Honorario de administración'), ('gasto', 'Gasto de la propiedad'))
    liquidacion = models.ForeignKey(Liquidacion, on_delete=models.CASCADE, related_name='lineas')
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name='+')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    descripcion = models.CharField(max_length=255)
    monto_usd = Monto(help_text='Con signo: el canon suma, el honorario y los gastos restan.')

    class Meta:
        ordering = ['id']


# --- Portal e ingresos externos -----------------------------------------------

class PortalAcceso(models.Model):
    """Enlace secreto de una persona (condómino, propietario o inquilino) a su estado de cuenta."""
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.CASCADE, related_name='accesos_portal')
    token = models.CharField(max_length=64, unique=True, editable=False)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultimo_acceso = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha_creacion']


class PagoReportado(models.Model):
    """Pago que el condómino/inquilino avisa desde su portal; la administradora lo revisa."""
    ESTADO_CHOICES = (('pendiente', 'Pendiente de revisión'), ('aprobado', 'Aprobado'), ('rechazado', 'Rechazado'))

    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name='pagos_reportados')
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='pagos_reportados')
    medio_pago = models.ForeignKey(MedioPago, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    metodo = models.CharField(max_length=15, choices=MedioPago.TIPO_CHOICES, default='transferencia')
    fecha_pago = models.DateField()
    referencia = models.CharField(max_length=100, blank=True, default='')
    banco = models.CharField(max_length=100, blank=True, default='')
    moneda_pago = models.CharField(max_length=3, default='VES')
    monto_pago = models.DecimalField(max_digits=16, decimal_places=2)
    cargos = models.ManyToManyField(Cargo, blank=True, related_name='pagos_reportados', help_text='Deudas que dice pagar (vacío = las más antiguas).')
    comprobante = models.FileField(upload_to=ruta_comprobantes, null=True, blank=True)
    nota = models.CharField(max_length=255, blank=True, default='')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pendiente')
    motivo_rechazo = models.CharField(max_length=255, blank=True, default='')
    recibo = models.OneToOneField(Recibo, on_delete=models.SET_NULL, null=True, blank=True, related_name='pago_reportado')
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_revision = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_creacion']


class ConsultaPropiedad(models.Model):
    """Persona interesada en una propiedad (formulario del portal público)."""
    ESTADO_CHOICES = (('nueva', 'Nueva'), ('contactada', 'Contactada'), ('cerrada', 'Cerrada'))
    unidad = models.ForeignKey(Unidad, on_delete=models.SET_NULL, null=True, blank=True, related_name='consultas')
    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=30)
    email = models.EmailField(blank=True, default='')
    mensaje = models.TextField(blank=True, default='')
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default='nueva')
    notas = models.TextField(blank=True, default='')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_creacion']
