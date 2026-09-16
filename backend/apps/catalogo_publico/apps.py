from django.apps import AppConfig


class CatalogoPublicoConfig(AppConfig):
    """
    App dedicada y aislada para todo lo que un cliente final anónimo puede
    hacer contra la tienda de un tenant: ver el catálogo y crear un pedido.

    Antes de esta app, la misma responsabilidad estaba repartida en dos
    implementaciones distintas dentro de `apps.facturacion` (una de ellas
    rota -- filtraba por un campo inexistente en el modelo). Consolidar todo
    lo `AllowAny` en un único app hace explícito, a nivel de arquitectura,
    dónde termina el panel privado y empieza la superficie pública.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.catalogo_publico'
    verbose_name = 'Catálogo Público'
