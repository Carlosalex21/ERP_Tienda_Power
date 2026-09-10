"""
Señales de invalidación de caché del catálogo de inventario.

Cuando un producto, variante o categoría cambia (crea, actualiza o elimina),
se invalida la caché del catálogo unificado y de categorías activas para que
el POS y el catálogo público reflejen inmediatamente los cambios, sin esperar
la expiración del TTL de Redis.
"""
from __future__ import annotations

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Categoriaproducto, Producto, Variacionproducto
from .services.catalog_service import invalidar_cache_catalogo


@receiver(post_save, sender=Producto)
def _invalidate_producto_save(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché del catálogo al crear/actualizar un producto."""
    invalidar_cache_catalogo()


@receiver(post_delete, sender=Producto)
def _invalidate_producto_delete(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché del catálogo al eliminar un producto."""
    invalidar_cache_catalogo()


@receiver(post_save, sender=Variacionproducto)
def _invalidate_variante_save(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché del catálogo al crear/actualizar una variante."""
    invalidar_cache_catalogo()


@receiver(post_delete, sender=Variacionproducto)
def _invalidate_variante_delete(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché del catálogo al eliminar una variante."""
    invalidar_cache_catalogo()


@receiver(post_save, sender=Categoriaproducto)
def _invalidate_categoria_save(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché del catálogo al crear/actualizar una categoría."""
    invalidar_cache_catalogo()


@receiver(post_delete, sender=Categoriaproducto)
def _invalidate_categoria_delete(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché del catálogo al eliminar una categoría."""
    invalidar_cache_catalogo()
