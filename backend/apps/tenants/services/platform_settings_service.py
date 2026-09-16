"""
Configuración global de la plataforma: cupo de registros gratuitos y
período de gracia tras vencer una suscripción.
"""
from __future__ import annotations

from .. import models as tenants_models


def obtener_configuracion() -> "tenants_models.PlatformSettings":
    config, _ = tenants_models.PlatformSettings.objects.get_or_create(pk=1)
    return config


def tenants_registrados() -> int:
    """Cantidad de tenants creados hasta ahora (todo registro arranca en prueba gratis)."""
    return tenants_models.Client.objects.exclude(schema_name='public').count()


def cupos_restantes() -> int | None:
    """`None` = sin límite configurado."""
    config = obtener_configuracion()
    if config.limite_registros_gratis is None:
        return None
    return max(config.limite_registros_gratis - tenants_registrados(), 0)


def hay_cupo_disponible() -> bool:
    restantes = cupos_restantes()
    return restantes is None or restantes > 0
