"""
Servicio de comprobantes de retención (ISLR / IVA) conforme al SENIAT.

Calcula el monto de retención a partir de una base y un porcentaje, y crea el
comprobante asociado a una factura de compra o a un proveedor.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction

from apps.configuracion.core.config_service import obtener_y_actualizar_numero_control

from apps.facturacion.models import Factura, Retencion

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


class RetencionServiceError(Exception):
    """Error controlado durante la creación de un comprobante de retención."""


def _round(value: Decimal) -> Decimal:
    """Redondea a 2 decimales con redondeo bancario."""
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def calcular_retencion(
    *,
    base: Decimal,
    tipo_retencion: str,
    porcentaje: Decimal,
) -> Decimal:
    """
    Calcula el monto de retención.

    Args:
        base: Base imponible sobre la que se aplica la retención.
        tipo_retencion: 'islr', 'iva' u 'otros'.
        porcentaje: Tasa porcentual (ej: 1 para 1 %).

    Returns:
        Decimal: Monto retenido, redondeado a 2 decimales.
    """
    if not ("islr" in tipo_retencion or "iva" in tipo_retencion or "otros" in tipo_retencion):
        raise RetencionServiceError(f"Tipo de retención inválido: {tipo_retencion}.")
    porcentaje = Decimal(porcentaje or 0)
    base = Decimal(base or 0)
    return _round(base * porcentaje / HUNDRED)


@transaction.atomic
def crear_comprobante_retencion(
    *,
    factura: Optional[Factura] = None,
    proveedor=None,
    tipo_retencion: str,
    porcentaje: Decimal,
    base: Decimal,
) -> Retencion:
    """
    Crea un comprobante de retención calculando el monto automáticamente.

    Args:
        factura: Factura de compra asociada (opcional).
        proveedor: Proveedor al que se le retiene (opcional).
        tipo_retencion: 'islr', 'iva' u 'otros'.
        porcentaje: Tasa porcentual (ej: 1 para 1 %).
        base: Base imponible sobre la que se aplica la retención.

    Returns:
        Retencion: El comprobante creado.

    Raises:
        RetencionServiceError: Si faltan factura y proveedor, la base es
            negativa o el porcentaje es inválido.
    """
    if factura is None and proveedor is None:
        raise RetencionServiceError(
            "Debe indicarse una factura o un proveedor para emitir la retención."
        )

    base = Decimal(base or 0)
    if base < 0:
        raise RetencionServiceError("La base de la retención no puede ser negativa.")
    if Decimal(porcentaje or 0) < 0:
        raise RetencionServiceError("El porcentaje de retención no puede ser negativo.")

    monto = calcular_retencion(
        base=base, tipo_retencion=tipo_retencion, porcentaje=porcentaje
    )
    numero_comprobante = obtener_y_actualizar_numero_control()

    return Retencion.objects.create(
        factura=factura,
        proveedor=proveedor,
        tipo_retencion=tipo_retencion,
        numero_comprobante=numero_comprobante,
        porcentaje=Decimal(porcentaje or 0),
        base=base,
        monto=monto,
    )
