from django.db import models
from django.conf import settings


class Horario(models.Model):
    nombre = models.CharField(max_length=100, default="Horario General")
    hora_entrada_oficial = models.TimeField()
    hora_salida_oficial = models.TimeField()
    margen_tardanza_minutos = models.PositiveIntegerField(default=5, help_text="Minutos de tolerancia para llegar tarde")

    def __str__(self):
        return self.nombre

# Días Festivos 
class DiaFestivo(models.Model):
    fecha = models.DateField(unique=True)
    descripcion = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.fecha.strftime('%d/%m/%Y')} - {self.descripcion}"

class Asistencia(models.Model):
    ESTADO_CHOICES = [
        ('Presente', 'Presente'),
        ('Ausente', 'Ausente'),
        ('Festivo', 'Festivo'),
        ('Medio Día', 'Medio Día'),
    ]
    
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    fecha = models.DateField()
    hora_entrada = models.DateTimeField(null=True, blank=True)
    hora_salida = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='Presente')
    # El estado actual del empleado en el día
    estado_actual = models.CharField(max_length=10, default='out') # out, in, break
    llegada_tarde = models.BooleanField(default=False)

    class Meta:
        unique_together = ('usuario', 'fecha') # Un solo registro por usuario y día
        ordering = ['-fecha']

class Descanso(models.Model):
    asistencia = models.ForeignKey(Asistencia, on_delete=models.CASCADE, related_name='descansos')
    inicio_descanso = models.DateTimeField()
    fin_descanso = models.DateTimeField(null=True, blank=True)