from django.apps import AppConfig


class InventarioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventario'

    def ready(self) -> None:
        """Registra las señales de invalidación de caché del catálogo."""
        from . import signals  # noqa: F401
