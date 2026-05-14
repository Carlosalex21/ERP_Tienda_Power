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