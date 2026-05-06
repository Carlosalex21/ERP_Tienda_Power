from django.db import transaction
from apps.configuracion.models import ConfiguracionCorrelativo

def obtener_y_actualizar_correlativo():
    """
    Bloquea la fila en la base de datos para evitar que dos facturas 
    salgan con el mismo número al mismo tiempo (Race condition).
    """
    with transaction.atomic():
        config = ConfiguracionCorrelativo.objects.select_for_update().first()
        if not config:
            config = ConfiguracionCorrelativo.objects.create(prefijo="F-", current_number=0)
        
        config.current_number += 1
        config.save()
        
        numero_formateado = str(config.current_number).zfill(config.number_length)
        return f"{config.prefijo}{numero_formateado}"