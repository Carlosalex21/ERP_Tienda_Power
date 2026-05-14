from django.db import transaction
from ..models import ConfiguracionCorrelativo

@transaction.atomic
def obtener_y_actualizar_correlativo():
    """
    Obtiene el siguiente número de correlativo de forma segura para evitar
    condiciones de carrera (race conditions).
    """
    # Bloquea la fila en la base de datos hasta que la transacción termine.
    config, _ = ConfiguracionCorrelativo.objects.select_for_update().get_or_create(pk=1)
    
    config.current_number += 1
    config.save()
    
    # Formatea el número con ceros a la izquierda (ej: F-001)
    numero_formateado = str(config.current_number).zfill(config.number_length)
    return f"{config.prefijo}{numero_formateado}"