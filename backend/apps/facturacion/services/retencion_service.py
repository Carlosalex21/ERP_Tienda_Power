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


def resolver_base_retencion(*, factura: Optional[Factura], tipo_retencion: str, base) -> Decimal:
    """
    Monto sobre el que se aplica el porcentaje de retención.

    - IVA (Providencia SNAT/2015/0049): se retiene un % (75 o 100) del
      IMPUESTO causado, no de la base imponible. Con factura asociada se toma
      su `iva_total` -- antes se usaba la base imponible y el monto retenido
      salía ~6 veces más alto de lo real (ej. 75% de la base en vez de 75%
      del IVA).
    - ISLR / otros: se aplica sobre la base imponible. Con factura asociada y
      sin base indicada, se toma su `base_imponible`.
    - Sin factura (retención directa a un proveedor): se respeta la base
      indicada, no hay documento del cual derivarla.
    """
    if factura is not None:
        if "iva" in tipo_retencion:
            return Decimal(factura.iva_total or 0)
        if not base:
            return Decimal(factura.base_imponible or 0)
    return Decimal(base or 0)


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
    periodo_imposicion: Optional[str] = None,
) -> Retencion:
    """
    Crea un comprobante de retención calculando el monto automáticamente.

    Args:
        factura: Factura de compra asociada (opcional).
        proveedor: Proveedor al que se le retiene (opcional).
        tipo_retencion: 'islr', 'iva' u 'otros'.
        porcentaje: Tasa porcentual (ej: 1 para 1 %, 75 para 75 %, 100 para 100 %).
        base: Base imponible sobre la que se aplica la retención.
        periodo_imposicion: Periodo fiscal que declara el proveedor (ej: "2026").

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

    base = resolver_base_retencion(factura=factura, tipo_retencion=tipo_retencion, base=base)
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
        periodo_imposicion=periodo_imposicion or None,
    )


@transaction.atomic
def actualizar_comprobante_retencion(retencion: Retencion, **cambios) -> Retencion:
    """
    Edita un comprobante recalculando base y monto -- antes la edición
    guardaba la nueva base/porcentaje pero dejaba el `monto` viejo (es de
    solo lectura en el serializer y nadie lo recalculaba). El número de
    comprobante no cambia.
    """
    for campo, valor in cambios.items():
        setattr(retencion, campo, valor)

    if retencion.factura is None and retencion.proveedor is None:
        raise RetencionServiceError(
            "Debe indicarse una factura o un proveedor para emitir la retención."
        )
    retencion.base = resolver_base_retencion(
        factura=retencion.factura, tipo_retencion=retencion.tipo_retencion, base=retencion.base,
    )
    if retencion.base < 0 or Decimal(retencion.porcentaje or 0) < 0:
        raise RetencionServiceError("La base y el porcentaje de la retención no pueden ser negativos.")
    retencion.monto = calcular_retencion(
        base=retencion.base, tipo_retencion=retencion.tipo_retencion, porcentaje=retencion.porcentaje,
    )
    retencion.save()
    return retencion
