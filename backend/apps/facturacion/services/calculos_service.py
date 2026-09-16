"""
Motor de cálculo de facturas conforme a las providencias del SENIAT.

Integra el **Patrón Strategy** de impuestos (``apps.configuracion.core.tax_strategy``)
para que el desglose (subtotal, base imponible, IVA, retención, total) sea
independiente del país y soporte **multi-moneda** con tasa de cambio.

Cuando la factura se emite en una moneda distinta a la base del tenant, se
calculan los totales en la moneda de la factura y se **consolidan** los montos
en moneda base (``_base``) para poder agregar en reportes.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from apps.configuracion.core.config_service import obtener_pais_tenant
from apps.configuracion.core.tax_strategy import TaxStrategyRegistry
from apps.configuracion.services.conversion_service import (
    MonedaNoEncontradaError,
    TasaNoDisponibleError,
    convertir,
    get_moneda_base,
    get_tasa_vigente,
)

from apps.facturacion.models import Detallefactura

CENT = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    """Redondea a 2 decimales con redondeo bancario."""
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def _resolve_strategy(country_code: str | None = None):
    """
    Resuelve la estrategia fiscal activa.

    Orden de resolución: ``country_code`` explícito (permite forzar un país
    puntual, ej. en tests) > país configurado del tenant
    (``ConfiguracionEmpresa.pais_codigo``) > ``settings.DEFAULT_TAX_COUNTRY``
    como último recurso.

    Args:
        country_code: Código de país (VE/CO/PE) para forzar la estrategia.
    """
    code = (country_code or obtener_pais_tenant() or getattr(settings, "DEFAULT_TAX_COUNTRY", "VE")).upper()
    return TaxStrategyRegistry(code).get_strategy()


def calcular_linea(detalle: Detallefactura, strategy):
    """
    Calcula el desglose de una línea (subtotal, IVA, total) usando la estrategia.

    El precio unitario se interpreta **con impuesto incluido** (precio final),
    por lo que se extrae la base imponible para no duplicar el IVA.

    Args:
        detalle: Instancia de ``Detallefactura``.
        strategy: Estrategia fiscal (``TaxStrategy``).

    Returns:
        dict: ``{subtotal_linea, iva_linea, total_linea}``.
    """
    precio_final_unitario = _round(detalle.precio_unitario)
    descuento_pct = detalle.descuento or Decimal("0.00")
    total_bruto_linea = precio_final_unitario * (detalle.cantidad or 0)
    total_linea_con_dto = total_bruto_linea * (Decimal("1") - descuento_pct / Decimal("100"))

    # Tasa de IVA desde la configuración del producto (o de la variante).
    tasa_iva = Decimal("0.00")
    config_iva = None
    if detalle.producto is not None:
        config_iva = detalle.producto.configuracion_iva
    if config_iva is None and detalle.variante is not None:
        config_iva = detalle.variante.producto.configuracion_iva
    if config_iva is not None:
        tasa_iva = Decimal(config_iva.porcentaje_iva or "0")

    # Extraer la base imponible del total (que YA incluye IVA) antes de
    # calcular el impuesto. Antes se le pasaba `total_linea_con_dto`
    # directamente a `calculate_tax` como si ya fuera la base pre-impuesto
    # -- cuya fórmula es `base * tasa/100` --, lo que sobreestima el IVA y
    # subestima la base en cada línea (ej: $67 con 16% daba IVA=10.72 y
    # base=56.28, en vez de los correctos IVA=9.24 y base=57.76). El total
    # cobrado al cliente no cambiaba (subtotal+iva siempre suma el total
    # ingresado), pero el desglose fiscal sí estaba mal -- el mismo cálculo
    # que ya usa correctamente `Producto.base_imponible`.
    if tasa_iva > 0:
        base_extraida = total_linea_con_dto / (Decimal("1") + tasa_iva / Decimal("100"))
    else:
        base_extraida = total_linea_con_dto

    monto_iva = strategy.calculate_tax(
        base=base_extraida,
        tax_rate=tasa_iva,
        tax_type="iva",
        exempt=(tasa_iva == Decimal("0")),
    )

    # Base imponible = total con descuento - IVA (descontado del precio final).
    subtotal_linea = _round(total_linea_con_dto - monto_iva)
    iva_linea = _round(monto_iva)
    total_linea = _round(subtotal_linea + iva_linea)

    return {
        "subtotal_linea": subtotal_linea,
        "iva_linea": iva_linea,
        "total_linea": total_linea,
    }


def recalcular_y_guardar_factura(factura, country_code: str | None = None) -> None:
    """
    Recalcula subtotales, base imponible, IVA y totales de una factura y sus
    detalles, aplicando la estrategia fiscal del tenant.

    También calcula la retención total si el tenant la tiene configurada y


    consolida los montos en moneda base cuando la factura se emite en una
    moneda distinta.

    Args:
        factura: Instancia de ``Factura``.
        country_code: Código de país (VE/CO/PE). Opcional; por defecto SENIAT.
    """
    strategy = _resolve_strategy(country_code)

    detalles = Detallefactura.objects.filter(factura=factura).select_related(
        "producto__configuracion_iva",
        "variante__producto__configuracion_iva",
    )

    total_subtotal = Decimal("0.00")
    total_iva = Decimal("0.00")
    detalles_a_actualizar: list[Detallefactura] = []

    for detalle in detalles:
        resultado = calcular_linea(detalle, strategy)
        detalle.subtotal_linea = resultado["subtotal_linea"]
        detalle.iva_linea = resultado["iva_linea"]
        detalle.total_linea = resultado["total_linea"]
        detalles_a_actualizar.append(detalle)
        total_subtotal += resultado["subtotal_linea"]
        total_iva += resultado["iva_linea"]

    if detalles_a_actualizar:
        Detallefactura.objects.bulk_update(
            detalles_a_actualizar,
            ["subtotal_linea", "iva_linea", "total_linea"],
        )

    # Descuento global a nivel de factura.
    descuento_global = factura.descuento_global or Decimal("0.00")
    base_imponible = _round(total_subtotal - descuento_global)

    # Retención ISLR (1 % / 2 % según agente) — configurable por la estrategia.
    retencion_pct = getattr(factura, "retencion_pct", Decimal("0.00")) or Decimal("0.00")
    retencion_total = strategy.calculate_withholding(
        base=base_imponible,
        withholding_rate=retencion_pct,
        withholding_type="islr",
    )

    factura.subtotal = _round(total_subtotal)
    factura.base_imponible = _round(base_imponible)
    factura.iva_total = _round(total_iva)
    factura.retencion_total = _round(retencion_total)
    # Total = base imponible + IVA - retención
    factura.total = _round(base_imponible + total_iva - retencion_total)

    # --- Multi-moneda: tasa de cambio y consolidación en moneda base ---
    if factura.moneda is not None:
        try:
            tasa = get_tasa_vigente(factura.moneda.codigo)
        except (MonedaNoEncontradaError, TasaNoDisponibleError):
            tasa = Decimal("1.000000")
        factura.tasa_cambio = tasa

        # Consolidación en moneda base (para reportes).
        factura.subtotal_base = _round(convertir(factura.subtotal, factura.moneda.codigo, _moneda_base_codigo()))
        factura.base_imponible_base = _round(convertir(factura.base_imponible, factura.moneda.codigo, _moneda_base_codigo()))
        factura.iva_base = _round(convertir(factura.iva_total, factura.moneda.codigo, _moneda_base_codigo()))
        factura.retencion_base = _round(convertir(factura.retencion_total, factura.moneda.codigo, _moneda_base_codigo()))
        factura.total_base = _round(convertir(factura.total, factura.moneda.codigo, _moneda_base_codigo()))
    else:
        factura.tasa_cambio = Decimal("1.000000")
        factura.subtotal_base = factura.subtotal
        factura.base_imponible_base = factura.base_imponible
        factura.iva_base = factura.iva_total
        factura.retencion_base = factura.retencion_total
        factura.total_base = factura.total

    factura.save(update_fields=[
        "subtotal",
        "base_imponible",
        "iva_total",
        "retencion_total",
        "total",
        "tasa_cambio",
        "subtotal_base",
        "base_imponible_base",
        "iva_base",
        "retencion_base",
        "total_base",
    ])


def _moneda_base_codigo() -> str:
    """Devuelve el código ISO de la moneda base del tenant."""
    try:
        return get_moneda_base().codigo
    except Exception:  # noqa: BLE001
        return "VES"
