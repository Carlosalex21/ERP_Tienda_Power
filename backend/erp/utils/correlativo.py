from erp.models import ConfiguracionCorrelativo

def obtener_configuracion_correlativo():
    config, created = ConfiguracionCorrelativo.objects.get_or_create(
        id=1,
        defaults={'prefijo': 'F-', 'current_number': 0, 'number_length': 3}
    )
    return config