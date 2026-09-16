"""
Servicios de configuración central del tenant.

Incluye:
    * ``obtener_y_actualizar_correlativo`` — correlativo de factura (SENIAT).
    * ``obtener_y_actualizar_numero_control`` — número de control SENIAT.
    * ``obtener_configuraciones`` — lectura cacheada de la configuración global.
"""
from __future__ import annotations

from typing import Any, Dict

from django.conf import settings
from django.db import transaction

from apps.core.cache_utils import cached, invalidate_pattern



from ..models import ConfiguracionCorrelativo


@transaction.atomic
def obtener_y_actualizar_correlativo() -> str:
    """
    Obtiene el siguiente número de correlativo de forma segura para evitar
    condiciones de carrera (race conditions).
    """
    # Bloquea la fila en la base de datos hasta que la transacción termine.
    config, _ = ConfiguracionCorrelativo.objects.select_for_update().get_or_create(pk=1)

    config.current_number += 1
    config.save(update_fields=["current_number"])

    # Formatea el número con ceros a la izquierda (ej: F-001)
    numero_formateado = str(config.current_number).zfill(config.number_length)
    return f"{config.prefijo}{numero_formateado}"


@transaction.atomic
def obtener_y_actualizar_numero_control() -> str:
    """
    Obtiene el siguiente **número de control SENIAT** de forma segura.

    Sigue el mismo patrón ``SELECT ... FOR UPDATE`` que el correlativo para
    evitar condiciones de carrera al emitir facturas, notas de crédito o notas
    de débito. El prefijo es configurable (ej: ``CTRL-``, ``NC-``).

    Returns:
        str: Número de control formateado (ej: ``CTRL-00001``).
    """
    config, _ = ConfiguracionCorrelativo.objects.select_for_update().get_or_create(pk=1)

    config.current_control_number += 1
    config.save(update_fields=["current_control_number"])

    numero_formateado = str(config.current_control_number).zfill(config.control_number_length)
    return f"{config.prefijo_numero_control}{numero_formateado}"


@transaction.atomic
def obtener_y_actualizar_numero_control_nota_credito() -> str:
    """
    Número de control SENIAT para una Nota de Crédito -- secuencia propia,
    independiente de la de facturas (ver comentario en
    `ConfiguracionCorrelativo.prefijo_numero_control_nota_credito`).
    """
    config, _ = ConfiguracionCorrelativo.objects.select_for_update().get_or_create(pk=1)

    config.current_control_number_nota_credito += 1
    config.save(update_fields=["current_control_number_nota_credito"])

    numero_formateado = str(config.current_control_number_nota_credito).zfill(config.control_number_length_nota_credito)
    return f"{config.prefijo_numero_control_nota_credito}{numero_formateado}"


@transaction.atomic
def obtener_y_actualizar_numero_control_nota_debito() -> str:
    """Número de control SENIAT para una Nota de Débito -- ver la función análoga de Nota de Crédito."""
    config, _ = ConfiguracionCorrelativo.objects.select_for_update().get_or_create(pk=1)

    config.current_control_number_nota_debito += 1
    config.save(update_fields=["current_control_number_nota_debito"])

    numero_formateado = str(config.current_control_number_nota_debito).zfill(config.control_number_length_nota_debito)
    return f"{config.prefijo_numero_control_nota_debito}{numero_formateado}"


@cached(ttl=settings.CACHE_TTL.get("configuraciones", 600), key_builder=lambda: ("configuraciones_globales",))
def obtener_configuraciones() -> Dict[str, Any]:
    """
    Lectura cacheada de la configuración global del tenant.

    Devuelve los parámetros fiscales y de empresa necesarios para el frontend
    (tasas de IVA activas, moneda base, número de control/comprobante).
    """
    from ..models import ConfiguracionEmpresa, Configuracioniva, Moneda

    ivas = list(
        Configuracioniva.objects.filter(activo=True).values(
            "id", "nombre", "porcentaje_iva"
        )
    )
    empresa = ConfiguracionEmpresa.objects.filter(pk=1).values(
        "nombre_comercial", "razon_social", "rif", "direccion", "telefono"
    ).first() or {}
    moneda_base = Moneda.objects.filter(es_predeterminada=True, activa=True).first()
    correlativo = ConfiguracionCorrelativo.objects.filter(pk=1).values(
        "prefijo",
        "current_number",
        "number_length",
        "prefijo_numero_control",
        "current_control_number",
        "control_number_length",
    ).first() or {}

    return {
        "empresa": empresa,
        "ivas": ivas,
        "moneda_base": (
            {
                "codigo": moneda_base.codigo,
                "nombre": moneda_base.nombre,
                "simbolo": moneda_base.simbolo,
            }
            if moneda_base
            else None
        ),
        "correlativo": correlativo,
    }


@cached(ttl=settings.CACHE_TTL.get("configuraciones", 600), key_builder=lambda: ("pais_tenant",))
def obtener_pais_tenant() -> str:
    """
    Devuelve el código de país fiscal configurado para el tenant activo.

    Lee ``ConfiguracionEmpresa.pais_codigo`` (sembrado por
    ``TenantService.create_tenant`` al dar de alta el inquilino). Si por
    algún motivo no existe la fila de configuración, cae a
    ``settings.DEFAULT_TAX_COUNTRY`` en vez de asumir Venezuela en silencio.
    """
    from ..models import ConfiguracionEmpresa

    empresa = ConfiguracionEmpresa.objects.filter(pk=1).values("pais_codigo").first()
    if empresa and empresa.get("pais_codigo"):
        return empresa["pais_codigo"]
    return getattr(settings, "DEFAULT_TAX_COUNTRY", "VE")


def invalidar_configuraciones() -> None:
    """Invalida las claves de caché relacionadas con la configuración global."""
    invalidate_pattern("configuraciones_globales")
    invalidate_pattern("tax_strategy")
    invalidate_pattern("configuracion_iva")
    invalidate_pattern("monedas")
    invalidate_pattern("tasas_cambio")
    invalidate_pattern("pais_tenant")


def _build_tax_strategy_key(country: str) -> tuple:
    """Construye la clave de caché para la estrategia fiscal de un país."""
    return ("tax_strategy", country.upper())


@cached(
    ttl=settings.CACHE_TTL.get("parametros_fiscales", 900),
    key_builder=_build_tax_strategy_key,
)
def obtener_tax_strategy_info(country: str = "VE") -> dict[str, Any]:
    """
    Devuelve la información de la estrategia fiscal (cacheada por país).

    Args:
        country: Código de país (VE/CO/PE).

    Returns:
        dict: ``{country_code, country_name, tax_rates, available_countries}``.
    """
    from .tax_strategy import TaxStrategyRegistry

    strategy = TaxStrategyRegistry(country).get_strategy()
    return {
        "country_code": strategy.country_code,
        "country_name": strategy.country_name,
        "tax_rates": strategy.get_tax_rates(),
        "available_countries": TaxStrategyRegistry.available_countries(),
    }
