from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.auditoria'
    verbose_name = 'Auditoría'

    def ready(self):
        # Conecta las señales genéricas de creación/actualización/baja para
        # todos los modelos "auditables" -- ver `signals.py`. Se hace aquí
        # (no al importar `models.py`) porque `ready()` es el único punto
        # donde Django garantiza que TODAS las apps ya están cargadas, así
        # que importar modelos de otras apps (Factura, Producto, etc.) es
        # seguro.
        from . import signals  # noqa: F401
