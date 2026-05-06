from django.db import transaction
from django.contrib.auth import get_user_model
from models import UserMetadata

User = get_user_model()

@transaction.atomic
def crear_empleado_service(user_data, metadata_data):
    """
    Servicio atómico para crear un usuario y su perfil asociado.
    """
    # Crear el usuario base
    user = User.objects.create_user(
        username=user_data['username'],
        password=user_data['password'],
        email=user_data.get('email', ''),
        first_name=user_data.get('first_name', ''),
        last_name=user_data.get('last_name', '')
    )
    
    # Generar número de empleado secuencial
    last_metadata = UserMetadata.objects.order_by('-id').first()
    next_id = (last_metadata.id + 1) if last_metadata else 1
    metadata_data['numero_empleado'] = f"EMP-{str(next_id).zfill(4)}"
    
    # Crear el perfil
    metadata = UserMetadata.objects.create(user=user, **metadata_data)
    
    return metadata