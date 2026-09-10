from django.apps import AppConfig


class ConfiguracionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.configuracion'

    def ready(self) -> None:
        """Registra las señales de invalidación de caché de configuración."""
        from . import signals  # noqa: F401
