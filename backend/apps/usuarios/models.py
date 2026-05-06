from django.db import models
from django.contrib.auth.models import User

class Rol(models.Model):
    nombre = models.CharField(unique=True, max_length=50)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'Rol'

    def __str__(self):
        return self.nombre

class Sesionusuario(models.Model):
    id = models.CharField(primary_key=True, max_length=32)
    datos = models.TextField()
    fecha_actualizacion = models.DateTimeField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'SesionUsuario'

class Logactividad(models.Model):
    usuario = models.ForeignKey('UserMetadata', models.DO_NOTHING, blank=True, null=True)
    accion = models.CharField(max_length=100)
    detalles = models.TextField(blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'LogActividad'

class UserMetadata(models.Model):
    # Relaciones Fundamentales 
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name="metadata"
    )
    rol = models.ForeignKey(
        'Rol', 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True
    )
    
    # Datos de Contacto y Personales
    telefono = models.CharField(max_length=15, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    foto_perfil = models.ImageField(upload_to='perfiles/', null=True, blank=True)
    
    # Datos Laborales y de Gestion
    puesto = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        help_text="El cargo del empleado (ej: Vendedor, Gerente)"
    )
    numero_empleado = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True, 
        null=True,
        help_text="Identificador único interno para el empleado"
    )
    fecha_contratacion = models.DateField(null=True, blank=True)
    almacen_asignado = models.ForeignKey(
        'inventario.Almacen', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Notas y Auditoria
    notas_internas = models.TextField(
        blank=True, 
        null=True,
        help_text="Notas privadas para administradores sobre el empleado."
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'UserMetadata'
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuarios"

    def __str__(self):
        full_name = self.user.get_full_name()
        return f"{full_name} ({self.user.username})" if full_name else self.user.username