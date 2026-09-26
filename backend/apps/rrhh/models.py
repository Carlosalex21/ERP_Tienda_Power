from django.db import models
from django.conf import settings

class Sucursal(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Sucursal")
    direccion = models.TextField(blank=True, null=True, verbose_name="Dirección")

    class Meta:
        verbose_name = "Sucursal"
        verbose_name_plural = "Sucursales"

    def __str__(self):
        return self.nombre


class Departamento(models.Model):
    """
    Equipo/área de trabajo del tenant (ej. "Cocina", "Barra", "Almacén",
    "Taller") -- generaliza el seguimiento de trabajo más allá de "un
    empleado nombrado": una orden de servicio, un plato en cocina o un
    pedido a preparar se puede asignar a un DEPARTAMENTO, y cualquier
    miembro de ese departamento (ver `apps.usuarios.UserMetadata.departamento`)
    puede marcarlo como avanzado, sin depender de que una persona puntual
    esté disponible. Aplica a cualquier vertical -- no es específico de
    servicios ni de restaurantes.
    """
    nombre = models.CharField(max_length=100, verbose_name="Nombre del Departamento")
    descripcion = models.CharField(max_length=255, blank=True, default='')
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

class Horario(models.Model):
    nombre = models.CharField(max_length=100, default="Horario General", verbose_name="Nombre del Horario")
    hora_entrada_oficial = models.TimeField(verbose_name="Hora de Entrada Oficial")
    hora_salida_oficial = models.TimeField(verbose_name="Hora de Salida Oficial")
    margen_tardanza_minutos = models.PositiveIntegerField(default=5, verbose_name="Margen de Tardanza (minutos)", help_text="Minutos de tolerancia para llegar tarde")

    class Meta:
        verbose_name = "Horario"
        verbose_name_plural = "Horarios"

    def __str__(self):
        return self.nombre

# Días Festivos 
class DiaFestivo(models.Model):
    fecha = models.DateField(unique=True, verbose_name="Fecha")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción")

    class Meta:
        verbose_name = "Día Festivo"
        verbose_name_plural = "Días Festivos"
        ordering = ['fecha']

    def __str__(self):
        return f"{self.fecha.strftime('%d/%m/%Y')} - {self.descripcion}"

class Asistencia(models.Model):
    ESTADO_CHOICES = [
        ('Presente', 'Presente'),
        ('Ausente', 'Ausente'),
        ('Festivo', 'Festivo'),
        ('Medio Día', 'Medio Día'),
    ]
    
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Usuario")
    fecha = models.DateField(verbose_name="Fecha")
    hora_entrada = models.DateTimeField(null=True, blank=True, verbose_name="Hora de Entrada")
    hora_salida = models.DateTimeField(null=True, blank=True, verbose_name="Hora de Salida")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='Presente', verbose_name="Estado del Día")
    # El estado actual del empleado en el día
    estado_actual = models.CharField(max_length=10, default='out', verbose_name="Estado Actual", help_text="Estado en tiempo real: out, in, break")
    llegada_tarde = models.BooleanField(default=False, verbose_name="Llegada Tarde")

    class Meta:
        unique_together = ('usuario', 'fecha') # Un solo registro por usuario y día
        ordering = ['-fecha']
        verbose_name = "Registro de Asistencia"
        verbose_name_plural = "Registros de Asistencia"

class Descanso(models.Model):
    asistencia = models.ForeignKey(Asistencia, on_delete=models.CASCADE, related_name='descansos', verbose_name="Asistencia Asociada")
    inicio_descanso = models.DateTimeField(verbose_name="Inicio del Descanso")
    fin_descanso = models.DateTimeField(null=True, blank=True, verbose_name="Fin del Descanso")

    class Meta:
        verbose_name = "Descanso"
        verbose_name_plural = "Descansos"
        ordering = ['-inicio_descanso']


class PeriodoNomina(models.Model):
    """
    Un período de nómina (ej. "1 al 15 de marzo") -- agrupa una línea
    `NominaEmpleado` por cada empleado con sueldo asignado. Se genera en
    'borrador' (revisable) y se marca 'pagada' aparte (ver
    `apps.rrhh.services.generar_periodo_nomina`/`pagar_periodo_nomina`),
    momento en el que recién genera su asiento contable automático -- igual
    que un asiento de venta no se genera hasta que el cobro es real.
    """
    ESTADO_CHOICES = (
        ('borrador', 'Borrador'),
        ('pagada', 'Pagada'),
    )
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='borrador')
    fecha_pago = models.DateTimeField(null=True, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'PeriodoNomina'
        ordering = ['-fecha_desde']
        verbose_name = 'Período de Nómina'
        verbose_name_plural = 'Períodos de Nómina'

    def __str__(self) -> str:
        return f'Nómina {self.fecha_desde} a {self.fecha_hasta}'


class NominaEmpleado(models.Model):
    """
    Línea de nómina de UN empleado en UN período -- snapshot de su sueldo al
    momento de generarse (si el sueldo del empleado cambia después, no
    reescribe nóminas ya generadas). `dias_ausencia` se calcula solo desde
    `Asistencia` (estado='Ausente') dentro del rango del período -- la
    automatización que liga asistencia real con lo que se le paga a cada
    quien, en vez de un monto fijo desconectado de si vino a trabajar.

    `horas_extra`/`pago_horas_extra` se calculan igual de automático, desde
    las horas realmente marcadas en `Asistencia` por encima del `Horario`
    oficial -- nunca un valor capturado a mano (ver
    `apps.rrhh.services._calcular_horas_extra`).

    `bonificaciones`/`otras_deducciones` son la SUMA de los `ConceptoNomina`
    recurrentes aplicados (ver `conceptos`, abajo) -- ya no un monto libre
    sin origen.
    """
    periodo = models.ForeignKey(PeriodoNomina, on_delete=models.CASCADE, related_name='empleados')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    sueldo_base = models.DecimalField(max_digits=12, decimal_places=2)
    dias_ausencia = models.PositiveIntegerField(default=0)
    deduccion_ausencias = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    horas_extra = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name="Horas Extra")
    pago_horas_extra = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Pago por Horas Extra")
    bonificaciones = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    otras_deducciones = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_pagar = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'NominaEmpleado'
        unique_together = [('periodo', 'usuario')]
        verbose_name = 'Línea de Nómina'
        verbose_name_plural = 'Líneas de Nómina'

    def __str__(self) -> str:
        return f'{self.usuario} - {self.periodo}'


class ConceptoNomina(models.Model):
    """
    Concepto de nómina configurable por el propio tenant -- un bono
    recurrente (ej. "Bono de Alimentación") o una deducción legal (ej.
    "Seguro Social Obligatorio") con el nombre/tasa que corresponda a SU
    país y régimen laboral.

    Deliberadamente NO se hardcodean tasas legales (IVSS, INCES, ISLR,
    parafiscales de CO/PE, etc.): varían por país (VE/CO/PE) y cambian con
    el tiempo -- el sistema solo da la infraestructura para que el usuario
    (o su contador) las configure una vez, y de ahí en adelante se aplican
    solas en cada nómina nueva (`recurrente=True`).
    """
    TIPO_CHOICES = (
        ('bono', 'Bono / Asignación'),
        ('deduccion', 'Deducción'),
    )
    MODO_CHOICES = (
        ('porcentaje', 'Porcentaje del sueldo base'),
        ('fijo', 'Monto fijo'),
    )
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    modo = models.CharField(max_length=10, choices=MODO_CHOICES, default='fijo')
    valor = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Porcentaje del sueldo base (ej. 4.00 = 4%) o monto fijo, según `modo`.",
    )
    recurrente = models.BooleanField(
        default=True,
        help_text="Si está activo, se aplica automáticamente a cada nómina nueva de cada empleado.",
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ConceptoNomina'
        ordering = ['tipo', 'nombre']
        verbose_name = 'Concepto de Nómina'
        verbose_name_plural = 'Conceptos de Nómina'

    def __str__(self) -> str:
        return self.nombre


class NominaEmpleadoConcepto(models.Model):
    """
    Snapshot de un `ConceptoNomina` ya aplicado a una línea de nómina -- si
    el concepto cambia de valor después (o se desactiva), no reescribe
    nóminas ya generadas, igual que `NominaEmpleado.sueldo_base` frente al
    sueldo actual del empleado.
    """
    nomina_empleado = models.ForeignKey(NominaEmpleado, on_delete=models.CASCADE, related_name='conceptos')
    concepto = models.ForeignKey(ConceptoNomina, on_delete=models.PROTECT, related_name='+')
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=ConceptoNomina.TIPO_CHOICES)
    monto = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'NominaEmpleadoConcepto'
        verbose_name = 'Concepto Aplicado a Nómina'
        verbose_name_plural = 'Conceptos Aplicados a Nómina'

    def __str__(self) -> str:
        return f'{self.nombre} ({self.nomina_empleado})'