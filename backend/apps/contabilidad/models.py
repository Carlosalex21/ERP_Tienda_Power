"""
Módulo de Contabilidad (partida doble) -- para tenants tipo_negocio='contador'
que llevan la contabilidad de varias empresas/clientes distintas, cada una
con su propio plan de cuentas y libros, separados de la facturación normal
del sistema (que sigue existiendo aparte para cobrarle honorarios al cliente).
"""
from django.conf import settings
from django.db import models, transaction


class EmpresaContable(models.Model):
    """
    Una empresa/cliente cuya contabilidad lleva este contador -- NO es lo
    mismo que `apps.clientes.Cliente` (a quién se le factura): esa es la
    entidad fiscal completa con su propio plan de cuentas y asientos. Se
    puede enlazar opcionalmente a un `Cliente` para poder facturarle
    honorarios profesionales sin duplicar sus datos de contacto/RIF.
    """
    nombre = models.CharField(max_length=200)
    identificacion_fiscal = models.CharField(
        max_length=30, blank=True, null=True,
        help_text="RIF/NIT/RUC de la empresa, según el país.",
    )
    cliente = models.ForeignKey(
        'clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='empresa_contable',
        help_text="Cliente asociado para poder facturarle honorarios profesionales (opcional).",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    # Marca la empresa contable que representa AL PROPIO TENANT (no a un
    # cliente del contador) -- cuando está marcada y tiene sus cuentas por
    # defecto configuradas, las ventas que el tenant registre por su cuenta
    # normal (POS, catálogo, etc.) generan su asiento automáticamente. Debería
    # haber como mucho una por tenant (no se fuerza a nivel de base de datos,
    # ver `EmpresaContableSerializer.validate`).
    es_negocio_propio = models.BooleanField(
        default=False,
        verbose_name='Es el negocio propio del tenant',
        help_text='Si se marca, las ventas normales del sistema (no solo honorarios) pueden generarle asiento automático.',
    )
    # Cuentas por defecto para el "Facturar Honorarios" (y, si aplica, para
    # el asiento automático de una venta normal del propio tenant -- ver
    # `services.generar_asiento_automatico_venta`) -- evita tener que
    # elegirlas a mano cada vez; se pueden dejar vacías y elegir manualmente.
    cuenta_cobro_default = models.ForeignKey(
        'CuentaContable', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', help_text='Cuenta a debitar por defecto al cobrar (ej. Caja/Bancos).',
    )
    cuenta_ingreso_default = models.ForeignKey(
        'CuentaContable', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', help_text='Cuenta a acreditar por defecto (ej. Ingresos por Honorarios/Ventas).',
    )
    cuenta_iva_default = models.ForeignKey(
        'CuentaContable', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', help_text='Cuenta de IVA por pagar, para separar el IVA del ingreso en el asiento automático.',
    )

    class Meta:
        db_table = 'EmpresaContable'
        ordering = ['nombre']
        verbose_name = 'Empresa Contable'
        verbose_name_plural = 'Empresas Contables'

    def __str__(self) -> str:
        return self.nombre


class CuentaContable(models.Model):
    """
    Una cuenta del plan de cuentas de una `EmpresaContable`. Jerárquica
    (`cuenta_padre`): las cuentas "de grupo" (ej. "1.1 Activo Corriente")
    organizan, y solo las hoja (`acepta_movimiento=True`) reciben
    movimientos reales en un asiento -- igual que cualquier plan de cuentas
    real, para no dejar cargar un asiento directamente a "1. Activo".
    """
    TIPO_CHOICES = (
        ('activo', 'Activo'),
        ('pasivo', 'Pasivo'),
        ('patrimonio', 'Patrimonio'),
        ('ingreso', 'Ingreso'),
        ('costo', 'Costo'),
        ('gasto', 'Gasto'),
    )
    # Determina si un débito o un crédito AUMENTA el saldo de la cuenta --
    # se deriva de `tipo` (ver `NATURALEZA_POR_TIPO` en services.py) pero se
    # guarda explícito para no recalcularlo en cada reporte y por si algún
    # día se necesita una excepción (cuenta de naturaleza contraria, ej. una
    # cuenta "Depreciación Acumulada" dentro de Activo).
    NATURALEZA_CHOICES = (
        ('deudora', 'Deudora (Débito)'),
        ('acreedora', 'Acreedora (Crédito)'),
    )

    empresa = models.ForeignKey(EmpresaContable, on_delete=models.CASCADE, related_name='cuentas')
    codigo = models.CharField(max_length=20, help_text='Ej. "1.1.01".')
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES)
    naturaleza = models.CharField(max_length=10, choices=NATURALEZA_CHOICES)
    cuenta_padre = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='subcuentas',
    )
    acepta_movimiento = models.BooleanField(
        default=True,
        verbose_name='Acepta movimiento',
        help_text='Falso para cuentas "de grupo" (organizan el plan pero no reciben asientos directamente).',
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'CuentaContable'
        ordering = ['codigo']
        unique_together = [('empresa', 'codigo')]
        verbose_name = 'Cuenta Contable'
        verbose_name_plural = 'Cuentas Contables'

    def __str__(self) -> str:
        return f'{self.codigo} - {self.nombre}'


class AsientoContable(models.Model):
    """
    Cabecera de un asiento contable (partida doble) -- sus líneas viven en
    `AsientoContableDetalle`. `numero` es un correlativo propio POR EMPRESA
    (no comparte numeración con el correlativo fiscal de facturación, que es
    de un negocio completamente distinto).
    """
    ESTADO_CHOICES = (
        ('borrador', 'Borrador'),
        ('contabilizado', 'Contabilizado'),
        ('anulado', 'Anulado'),
    )
    ORIGEN_CHOICES = (
        ('manual', 'Manual'),
        ('honorarios', 'Facturación de Honorarios'),
        ('venta', 'Venta del Sistema'),
        ('cierre', 'Cierre de Ejercicio'),
    )

    empresa = models.ForeignKey(EmpresaContable, on_delete=models.PROTECT, related_name='asientos')
    numero = models.PositiveIntegerField(editable=False)
    fecha = models.DateField()
    descripcion = models.CharField(max_length=255)
    # 'borrador' -- un asiento que el contador está armando/revisando y
    # todavía no quiere que cuente en los reportes (todos los reportes
    # filtran `estado='contabilizado'`, así que un borrador es invisible
    # para libro mayor/balance/estados hasta que se contabilice).
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='contabilizado')
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES, default='manual')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_anulacion = models.DateTimeField(null=True, blank=True)
    # Foto/PDF del recibo o factura que soporta este asiento -- opcional,
    # se puede adjuntar al crear el asiento o después.
    comprobante = models.FileField(upload_to='comprobantes_contables/', blank=True, null=True)

    class Meta:
        db_table = 'AsientoContable'
        ordering = ['-fecha', '-numero']
        unique_together = [('empresa', 'numero')]
        verbose_name = 'Asiento Contable'
        verbose_name_plural = 'Asientos Contables'

    def __str__(self) -> str:
        return f'Asiento {self.numero} - {self.empresa.nombre}'

    def save(self, *args, **kwargs):
        if not self.numero:
            # `select_for_update` sobre el último asiento DE ESTA EMPRESA --
            # mismo patrón que `OrdenServicio.numero`, para que dos asientos
            # creados casi al mismo tiempo para la misma empresa no choquen
            # con el mismo número (empresas distintas sí pueden compartir
            # número, cada una lleva su propia numeración).
            with transaction.atomic():
                ultimo = (
                    AsientoContable.objects.select_for_update()
                    .filter(empresa=self.empresa)
                    .order_by('-numero')
                    .first()
                )
                self.numero = (ultimo.numero + 1) if ultimo else 1
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


class AsientoContableDetalle(models.Model):
    """
    Una línea de un asiento -- debe tener `debe` O `haber` (nunca ambos, ni
    ninguno), y la suma de todas las líneas de un mismo asiento debe
    cuadrar (ver `services.crear_asiento_contable`, que es la única vía
    soportada para crear asientos -- así la validación de partida doble
    nunca se puede saltar creando detalles sueltos).
    """
    asiento = models.ForeignKey(AsientoContable, on_delete=models.CASCADE, related_name='detalles')
    cuenta = models.ForeignKey(CuentaContable, on_delete=models.PROTECT, related_name='movimientos')
    debe = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    haber = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    orden = models.PositiveIntegerField(default=0)
    # Conciliación bancaria: si este movimiento (de una cuenta Caja/Banco) ya
    # se cruzó contra el estado de cuenta real del banco.
    conciliado = models.BooleanField(default=False)
    fecha_conciliacion = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'AsientoContableDetalle'
        ordering = ['orden', 'id']
        verbose_name = 'Detalle de Asiento'
        verbose_name_plural = 'Detalles de Asiento'

    def __str__(self) -> str:
        return f'{self.cuenta.codigo} D:{self.debe} H:{self.haber}'


class AsientoPlantilla(models.Model):
    """
    Plantilla reutilizable de un asiento que se repite seguido (ej. alquiler
    mensual, nómina) -- guarda la estructura de líneas (cuentas + montos
    típicos) para no volver a tipear lo mismo cada mes. El contador la usa
    para PRE-LLENAR el formulario de "Nuevo Asiento"; no genera asientos
    solo -- no hay infraestructura de tareas programadas confiable en este
    proyecto todavía como para automatizar la generación sin riesgo de fallar
    en silencio y dejar un mes sin registrar.
    """
    empresa = models.ForeignKey(EmpresaContable, on_delete=models.CASCADE, related_name='plantillas')
    nombre = models.CharField(max_length=150, help_text='Ej. "Alquiler mensual", "Nómina quincenal".')
    descripcion_asiento = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Descripción que traerá el asiento al usar esta plantilla (se puede editar antes de guardar).',
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'AsientoPlantilla'
        ordering = ['nombre']
        verbose_name = 'Plantilla de Asiento'
        verbose_name_plural = 'Plantillas de Asiento'

    def __str__(self) -> str:
        return self.nombre


class AsientoPlantillaLinea(models.Model):
    plantilla = models.ForeignKey(AsientoPlantilla, on_delete=models.CASCADE, related_name='lineas')
    cuenta = models.ForeignKey(CuentaContable, on_delete=models.PROTECT, related_name='+')
    debe = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    haber = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'AsientoPlantillaLinea'
        ordering = ['orden', 'id']
        verbose_name = 'Línea de Plantilla'
        verbose_name_plural = 'Líneas de Plantilla'


class CierreEjercicio(models.Model):
    """
    Registro de un cierre de ejercicio -- deja constancia de que un período
    ya se cerró (Ingresos/Costos/Gastos contra Patrimonio) y con qué asiento,
    para no poder cerrarlo dos veces por accidente ni volver a mostrarlo
    "abierto" en los reportes.
    """
    empresa = models.ForeignKey(EmpresaContable, on_delete=models.CASCADE, related_name='cierres')
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    asiento = models.OneToOneField(AsientoContable, on_delete=models.PROTECT, related_name='cierre_ejercicio')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'CierreEjercicio'
        ordering = ['-fecha_hasta']
        verbose_name = 'Cierre de Ejercicio'
        verbose_name_plural = 'Cierres de Ejercicio'

    def __str__(self) -> str:
        return f'Cierre {self.empresa.nombre} {self.fecha_desde}..{self.fecha_hasta}'
