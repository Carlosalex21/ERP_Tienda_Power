from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ClienteB2B, InvitacionB2B

@receiver(post_save, sender=ClienteB2B)
def crear_invitacion_para_nuevo_cliente_b2b(sender, instance, created, **kwargs):
    """
    Crea automáticamente una InvitacionB2B cuando se crea un nuevo ClienteB2B,
    asegurando que siempre exista una invitación asociada.
    """
    if created:
        # get_or_create es seguro en caso de que otro proceso la cree simultáneamente.
        InvitacionB2B.objects.get_or_create(cliente_b2b=instance, defaults={'email': instance.email_contacto})