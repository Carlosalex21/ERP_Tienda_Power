from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from apps.usuarios.models import Logactividad, UserMetadata
from apps.facturacion.models import Factura, Detallefactura
from apps.inventario.models import Producto, Variacionproducto
from apps.clientes.models import Cliente

User = get_user_model()

@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    # Ignorar modelos que no queremos loggear o que son el propio Logactividad
    if sender in [Logactividad, User, UserMetadata]:
        return

    action = "creado" if created else "actualizado"
    details = f"{sender.__name__} con ID {instance.pk} {action}."
    
    # Intenta obtener el usuario de la petición si está disponible (requiere middleware)
    # Esto es más complejo y a menudo se hace con un middleware que guarda el usuario en un thread-local
    # Por simplicidad, aquí no lo implementaremos, pero es la idea.
    usuario = None # TODO: Implementar middleware para obtener el usuario de la petición

    Logactividad.objects.create(usuario=usuario, accion=action, detalles=details)

@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    if sender in [Logactividad, User, UserMetadata]:
        return
    
    details = f"{sender.__name__} con ID {instance.pk} eliminado."
    usuario = None # TODO: Implementar middleware para obtener el usuario de la petición
    Logactividad.objects.create(usuario=usuario, accion="eliminado", detalles=details)