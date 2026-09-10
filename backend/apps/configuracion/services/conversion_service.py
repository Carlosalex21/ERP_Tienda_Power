"""
Servicio de conversión de monedas (multi-moneda).

Centraliza la resolución de la moneda base del tenant, la lectura de tasas
vigentes (cacheadas en Redis) y la conversión de montos entre divisas para
soportar facturación simultánea en múltiples monedas.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.conf import settings

from apps.core.cache_utils import cached, invalidate_pattern

from ..models import Moneda, TasaCambio

CENT = Decimal("0.01")


class MonedaNoEncontradaError(Exception):
    """Se dispara cuando se solicita una moneda inexistente o inactiva."""


class TasaNoDisponibleError(Exception):
    """Se dispara cuando no hay una tasa vigente para la conversión."""


def _round_money(value: Decimal) -> Decimal:
    """Redondea a 2 decimales con redondeo bancario (half-up)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def get_moneda_base() -> Moneda:
    """
    Devuelve la moneda base (predeterminada) del tenant.

    Returns:
        Moneda: La moneda con ``es_predeterminada=True``.

    Raises:
        MonedaNoEncontradaError: Si el tenant no tiene una moneda base activa.
    """
    moneda = Moneda.objects.filter(es_predeterminada=True, activa=True).first()
    if moneda is None:
        moneda = Moneda.objects.filter(activa=True).first()
    if moneda is None:
        raise MonedaNoEncontradaError(
            "El tenant no tiene una moneda base configurada."
        )
    return moneda


def _build_tasa_key(codigo_moneda: str) -> tuple:
    """Construye la clave de caché para la tasa vigente de una moneda."""
    return ("tasa_vigente", codigo_moneda.upper())


def invalidar_tasas_cambio() -> None:
    """Invalida las claves de caché de tasas de cambio."""
    invalidate_pattern("tasa_vigente")
    invalidate_pattern("monedas")
    invalidate_pattern("tasas_cambio")
    invalidate_pattern("configuraciones_globales")


@cached(
    ttl=settings.CACHE_TTL.get("parametros_fiscales", 900),
    key_builder=_build_tasa_key,
)
def get_tasa_vigente(codigo_moneda: str) -> Decimal:
    """
    Obtiene la tasa vigente de una moneda frente a la moneda base.

    La tasa se interpreta como: ``1 unidad de la moneda = tasa unidades de
    la moneda base``. Se cachea en Redis por tenant.

    Args:
        codigo_moneda: Código ISO de la moneda (ej: 'USD', 'EUR').

    Returns:
        Decimal: Tasa vigente.

    Raises:
        MonedaNoEncontradaError: Si la moneda no existe o está inactiva.
        TasaNoDisponibleError: Si la moneda no tiene una tasa vigente.
    """
    codigo = codigo_moneda.upper()
    moneda = Moneda.objects.filter(codigo=codigo, activa=True).first()
    if moneda is None:
        raise MonedaNoEncontradaError(f"La moneda '{codigo_moneda}' no existe.")

    # La moneda base tiene tasa = 1.
    if moneda.es_predeterminada:
        return Decimal("1.000000")

    tasa = (
        TasaCambio.objects.filter(moneda=moneda, activa=True)
        .order_by("-fecha", "-id")
        .values_list("tasa", flat=True)
        .first()
    )
    if tasa is None:
        raise TasaNoDisponibleError(
            f"No hay una tasa de cambio vigente para '{codigo_moneda}'."
        )
    return Decimal(tasa)


def convertir(
    monto: Decimal,
    from_codigo: str,
    to_codigo: str,
) -> Decimal:
    """
    Convierte un monto de una moneda a otra usando las tasas vigentes.

    Si ``from_codigo`` o ``to_codigo`` es la moneda base, la conversión es
    directa. En caso contrario, se convierte primero a la moneda base y luego
    a la moneda destino.

    Args:
        monto: Monto a convertir.
        from_codigo: Código de la moneda origen.
        to_codigo: Código de la moneda destino.

    Returns:
        Decimal: Monto convertido, redondeado a 2 decimales.
    """
    monto = Decimal(monto or 0)
    if from_codigo.upper() == to_codigo.upper():
        return _round_money(monto)

    tasa_origen = get_tasa_vigente(from_codigo)
    tasa_destino = get_tasa_vigente(to_codigo)

    # Convierte a la moneda base y luego a la moneda destino.
    en_base = monto / tasa_origen
    convertido = en_base * tasa_destino
    return _round_money(convertido)


def _build_tasas_actuales_key() -> tuple:
    """Construye la clave de caché para el listado de tasas vigentes."""
    return ("tasas_actuales",)


@cached(
    ttl=settings.CACHE_TTL.get("parametros_fiscales", 900),
    key_builder=_build_tasas_actuales_key,
)
def obtener_tasas_actuales() -> dict[str, dict]:
    """
    Devuelve las tasas vigentes de todas las monedas activas (no base).

    La moneda base se reporta con tasa ``1.000000``. Las monedas sin tasa
    vigente se reportan con ``tasa=None`` para que el frontend lo muestre
    como pendiente de configuración.

    Returns:
        dict: ``{codigo_moneda: {codigo, nombre, simbolo, tasa, es_base}}``.
    """
    monedas = Moneda.objects.filter(activa=True).order_by("-es_predeterminada", "codigo")
    resultado: dict[str, dict] = {}
    for moneda in monedas:
        try:
            tasa = get_tasa_vigente(moneda.codigo)
        except (MonedaNoEncontradaError, TasaNoDisponibleError):
            tasa = None
        resultado[moneda.codigo] = {
            "codigo": moneda.codigo,
            "nombre": moneda.nombre,
            "simbolo": moneda.simbolo,
            "tasa": str(tasa) if tasa is not None else None,
            "es_base": bool(moneda.es_predeterminada),
        }
    return resultado
