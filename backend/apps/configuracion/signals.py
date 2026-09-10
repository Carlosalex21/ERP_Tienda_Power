"""
Señales de invalidación de caché de la configuración fiscal.

Cuando cambian las monedas, tasas de cambio, configuraciones de IVA o el
correlativo/número de control, se invalidan las claves de Redis asociadas
para que la configuración global, la estrategia fiscal y las tasas vigentes
se refresquen de inmediato.
"""
from __future__ import annotations

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import (
    ConfiguracionCorrelativo,
    Configuracioniva,
    Moneda,
    TasaCambio,
)
from .core.config_service import invalidar_configuraciones
from .services.conversion_service import invalidar_tasas_cambio


@receiver(post_save, sender=Moneda)
def _invalidate_moneda_save(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché de configuraciones y tasas al crear/actualizar moneda."""
    invalidar_configuraciones()
    invalidar_tasas_cambio()


@receiver(post_delete, sender=Moneda)
def _invalidate_moneda_delete(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché de configuraciones y tasas al eliminar moneda."""
    invalidar_configuraciones()
    invalidar_tasas_cambio()


@receiver(post_save, sender=TasaCambio)
def _invalidate_tasa_save(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché de tasas al crear/actualizar una tasa de cambio."""
    invalidar_tasas_cambio()
    invalidar_configuraciones()


@receiver(post_delete, sender=TasaCambio)
def _invalidate_tasa_delete(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché de tasas al eliminar una tasa de cambio."""
    invalidar_tasas_cambio()
    invalidar_configuraciones()


@receiver(post_save, sender=Configuracioniva)
def _invalidate_iva_save(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché de configuraciones al crear/actualizar IVA."""
    invalidar_configuraciones()


@receiver(post_delete, sender=Configuracioniva)
def _invalidate_iva_delete(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché de configuraciones al eliminar un IVA."""
    invalidar_configuraciones()


@receiver(post_save, sender=ConfiguracionCorrelativo)
def _invalidate_correlativo_save(sender, instance, **kwargs):  # noqa: ARG001
    """Invalida la caché de configuraciones al cambiar el correlativo."""
    invalidar_configuraciones()
