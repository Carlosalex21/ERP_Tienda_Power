from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from apps.rrhh.models import Sucursal # Importamos el modelo Sucursal

class Rol(models.Model):
    # Código estable para autorización (ver apps.core.permissions). A
    # diferencia de `nombre` -- editable libremente desde el panel -- el
    # `codigo` es el identificador que el código de permisos compara, así
    # renombrar el rol visible no rompe la autorización en silencio.
    codigo = models.CharField(
        max_length=30, unique=True, null=True, blank=True,
        verbose_name="Código", help_text="Identificador estable usado por el sistema de permisos (ej: 'admin', 'vendedor').",
    )
    nombre = models.CharField(unique=True, max_length=50, verbose_name="Nombre del Rol")
    descripcion = models.TextField(blank=True, null=True, verbose_name="Descripción")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    # Códigos de módulo (ver `ERP_System_Persona/src/utils/modulosPanel.ts`,
    # la lista canónica que también arma el menú lateral) que este rol NO
    # debe ver en el panel. Antes no existía forma de personalizar el menú
    # por rol -- un cajero veía exactamente las mismas opciones que un
    # administrador, solo que el backend le bloqueaba la acción al
    # intentarla. Es una lista simple (no un modelo aparte por
    # rol×módulo) a propósito: un solo campo es más fácil de armar en el
    # panel y de razonar que una tabla de asociación para ~25 módulos fijos.
    modulos_ocultos = models.JSONField(default=list, blank=True, verbose_name="Módulos ocultos")

    class Meta:
        db_table = 'Rol'
        verbose_name = "Rol de Usuario"
        verbose_name_plural = "Roles de Usuario"

    def __str__(self):
        return self.nombre

class Sesionusuario(models.Model):
    id = models.CharField(primary_key=True, max_length=32, verbose_name="ID de Sesión")
    datos = models.TextField(verbose_name="Datos de Sesión")
    fecha_actualizacion = models.DateTimeField(blank=True, null=True, verbose_name="Última Actualización")
    activo = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        db_table = 'SesionUsuario'
        verbose_name = "Sesión de Usuario"
        verbose_name_plural = "Sesiones de Usuarios"

class Logactividad(models.Model):
    usuario = models.ForeignKey('UserMetadata', models.SET_NULL, blank=True, null=True, verbose_name="Usuario")
    accion = models.CharField(max_length=100, verbose_name="Acción")
    detalles = models.TextField(blank=True, null=True, verbose_name="Detalles")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha y Hora")

    class Meta:
        db_table = 'LogActividad'
        verbose_name = "Log de Actividad"
        verbose_name_plural = "Logs de Actividad"
        ordering = ['-fecha']

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
        null=True,
        verbose_name="Rol"
    )
    sucursal = models.ForeignKey(
        Sucursal, 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        verbose_name="Sucursal Asignada"
    )
    
    # Datos de Contacto y Personales
    telefono = models.CharField(max_length=15, blank=True, null=True, verbose_name="Teléfono")
    direccion = models.TextField(blank=True, null=True, verbose_name="Dirección")
    fecha_nacimiento = models.DateField(null=True, blank=True, verbose_name="Fecha de Nacimiento")
    foto_perfil = models.ImageField(upload_to='perfiles/', null=True, blank=True, verbose_name="Foto de Perfil")
    
    # Datos Laborales y de Gestion
    puesto = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        help_text="El cargo del empleado (ej: Vendedor, Gerente)",
        verbose_name="Puesto"
    )
    numero_empleado = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True, 
        null=True,
        help_text="Identificador único interno para el empleado",
        verbose_name="Número de Empleado"
    )
    fecha_contratacion = models.DateField(null=True, blank=True, verbose_name="Fecha de Contratación")
    almacen_asignado = models.ForeignKey(
        'inventario.Almacen', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Almacén Asignado"
    )
    
    # Notas y Auditoria
    notas_internas = models.TextField(
        blank=True, 
        null=True,
        help_text="Notas privadas para administradores sobre el empleado.",
        verbose_name="Notas Internas"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    fecha_modificacion = models.DateTimeField(auto_now=True, verbose_name="Última Modificación")
    # --- Seguridad: bloqueo temporal por intentos fallidos de login ---
    bloqueado_hasta = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Bloqueado hasta",
        help_text="Fecha/hora hasta la que la cuenta queda bloqueada por intentos fallidos.",
    )

    class Meta:
        db_table = 'UserMetadata'
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuarios"

    def __str__(self):
        full_name = self.user.get_full_name()
        return f"{full_name} ({self.user.username})" if full_name else self.user.username


class LoginAttempt(models.Model):
    """
    Registro de intentos de inicio de sesión (Zero Trust).

    Se usa para contar los intentos fallidos dentro de una ventana de tiempo
    y bloquear temporalmente la cuenta del usuario, evitando fuerza bruta.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="login_attempts",
        verbose_name="Usuario",
    )
    ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="Dirección IP",
    )
    success = models.BooleanField(default=False, verbose_name="¿Éxito?")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora")

    class Meta:
        db_table = 'LoginAttempt'
        verbose_name = "Intento de Inicio de Sesión"
        verbose_name_plural = "Intentos de Inicio de Sesión"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp'], name='idx_login_user_ts'),
        ]

    def __str__(self) -> str:
        estado = "éxito" if self.success else "fallo"
        return f"{self.user.username}: {estado} desde {self.ip or 'desconocida'} ({self.timestamp})"
