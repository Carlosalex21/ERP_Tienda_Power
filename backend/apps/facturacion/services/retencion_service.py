"""
Servicio de comprobantes de retención (ISLR / IVA) conforme al SENIAT.

Calcula el monto de retención a partir de una base y un porcentaje, y crea el
comprobante asociado a una factura de compra o a un proveedor.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction

from apps.configuracion.core.config_service import obtener_y_actualizar_numero_retencion

from apps.facturacion.models import Factura, Retencion

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


class RetencionServiceError(Exception):
    """Error controlado durante la creación de un comprobante de retención."""


def _round(value: Decimal) -> Decimal:
    """Redondea a 2 decimales con redondeo bancario."""
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def resolver_base_retencion(*, factura: Optional[Factura], tipo_retencion: str, base, factura_compra=None) -> Decimal:
    """
    Monto sobre el que se aplica el porcentaje de retención.

    - IVA (Providencia SNAT/2015/0049): se retiene un % (75 o 100) del
      IMPUESTO causado, no de la base imponible. Con factura asociada se toma
      su IVA -- antes se usaba la base imponible y el monto retenido salía
      ~6 veces más alto de lo real (ej. 75% de la base en vez de 75% del IVA).
    - ISLR / otros: se aplica sobre la base imponible. Con factura asociada y
      sin base indicada, se toma su base imponible.
    - Sin factura (retención directa a un proveedor): se respeta la base
      indicada, no hay documento del cual derivarla.
    """
    if factura_compra is not None:
        if "iva" in tipo_retencion:
            return Decimal(factura_compra.iva or 0)
        if not base:
            return Decimal(factura_compra.base_imponible or 0)
        return Decimal(base)
    if factura is not None:
        if "iva" in tipo_retencion:
            return Decimal(factura.iva_total or 0)
        if not base:
            return Decimal(factura.base_imponible or 0)
    return Decimal(base or 0)


def _sincronizar_factura_compra(retencion: Retencion) -> None:
    """Rebaja la deuda con el proveedor y actualiza el Libro de Compras (ver `recalcular_retenciones_factura`)."""
    if retencion.factura_compra_id is None:
        return
    from apps.proveedores.core.facturas_compra_service import FacturaCompraError, recalcular_retenciones_factura
    try:
        recalcular_retenciones_factura(retencion.factura_compra)
    except FacturaCompraError as exc:
        raise RetencionServiceError(str(exc)) from exc


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


def _validar_vinculo(*, factura, factura_compra, proveedor) -> None:
    if factura is None and factura_compra is None and proveedor is None:
        raise RetencionServiceError(
            "Debe indicarse una factura de compra, un proveedor o una factura de venta."
        )
    if factura is not None and factura_compra is not None:
        raise RetencionServiceError("Una retención es sobre una factura de compra o sobre una de venta, no ambas.")
    if factura_compra is not None and factura_compra.estado == "anulada":
        raise RetencionServiceError("La factura de compra está anulada.")


@transaction.atomic
def crear_comprobante_retencion(
    *,
    factura: Optional[Factura] = None,
    factura_compra=None,
    proveedor=None,
    tipo_retencion: str,
    porcentaje: Decimal,
    base: Decimal,
    periodo_imposicion: Optional[str] = None,
    numero_comprobante: Optional[str] = None,
) -> Retencion:
    """
    Crea un comprobante de retención calculando el monto automáticamente.

    Args:
        factura: Factura de VENTA sobre la que un cliente le retuvo al
            negocio (retención recibida; su número lo trae el cliente en
            `numero_comprobante`).
        factura_compra: Factura de un proveedor sobre la que el negocio
            retiene (retención emitida).
        proveedor: Proveedor al que se le retiene sin factura asociada.
        tipo_retencion: 'islr', 'iva' u 'otros'.
        porcentaje: Tasa porcentual (ej: 1 para 1 %, 75 para 75 %, 100 para 100 %).
        base: Base imponible sobre la que se aplica la retención.
        periodo_imposicion: Periodo fiscal que declara el proveedor (ej: "2026").

    Raises:
        RetencionServiceError: Si no hay vínculo, la base es negativa o el
            porcentaje es inválido.
    """
    _validar_vinculo(factura=factura, factura_compra=factura_compra, proveedor=proveedor)
    if factura_compra is not None:
        proveedor = factura_compra.proveedor

    base = resolver_base_retencion(
        factura=factura, factura_compra=factura_compra, tipo_retencion=tipo_retencion, base=base,
    )
    if base < 0:
        raise RetencionServiceError("La base de la retención no puede ser negativa.")
    if Decimal(porcentaje or 0) < 0:
        raise RetencionServiceError("El porcentaje de retención no puede ser negativo.")

    monto = calcular_retencion(
        base=base, tipo_retencion=tipo_retencion, porcentaje=porcentaje
    )
    if factura is None:
        # Emitida por el negocio: numeración propia SENIAT (AAAAMM + 8),
        # independiente del número de control de las facturas de venta.
        numero_comprobante = obtener_y_actualizar_numero_retencion(tipo_retencion)
    else:
        numero_comprobante = (numero_comprobante or "").strip() or None

    retencion = Retencion.objects.create(
        factura=factura,
        factura_compra=factura_compra,
        proveedor=proveedor,
        tipo_retencion=tipo_retencion,
        numero_comprobante=numero_comprobante,
        porcentaje=Decimal(porcentaje or 0),
        base=base,
        monto=monto,
        periodo_imposicion=periodo_imposicion or None,
    )
    _sincronizar_factura_compra(retencion)
    if factura_compra is not None:
        from apps.contabilidad.services import generar_asiento_automatico_retencion_proveedor
        retencion.asiento = generar_asiento_automatico_retencion_proveedor(retencion)
        retencion.save(update_fields=["asiento"])
    return retencion


@transaction.atomic
def actualizar_comprobante_retencion(retencion: Retencion, **cambios) -> Retencion:
    """
    Edita un comprobante recalculando base y monto -- antes la edición
    guardaba la nueva base/porcentaje pero dejaba el `monto` viejo (es de
    solo lectura en el serializer y nadie lo recalculaba). El número de un
    comprobante emitido no cambia; el de uno recibido (de un cliente) sí se
    puede corregir.
    """
    factura_compra_anterior = retencion.factura_compra
    numero_anterior = retencion.numero_comprobante
    era_recibida = retencion.factura_id is not None
    for campo, valor in cambios.items():
        setattr(retencion, campo, valor)
    if retencion.factura_id is None:
        # Emitida: conserva su número, o recibe uno propio si antes era una
        # retención recibida (cuyo número era el del cliente).
        retencion.numero_comprobante = (
            numero_anterior if numero_anterior and not era_recibida
            else obtener_y_actualizar_numero_retencion(retencion.tipo_retencion)
        )
    else:
        retencion.numero_comprobante = (retencion.numero_comprobante or "").strip() or None

    _validar_vinculo(factura=retencion.factura, factura_compra=retencion.factura_compra, proveedor=retencion.proveedor)
    if retencion.factura_compra is not None:
        retencion.proveedor = retencion.factura_compra.proveedor
    retencion.base = resolver_base_retencion(
        factura=retencion.factura, factura_compra=retencion.factura_compra,
        tipo_retencion=retencion.tipo_retencion, base=retencion.base,
    )
    if retencion.base < 0 or Decimal(retencion.porcentaje or 0) < 0:
        raise RetencionServiceError("La base y el porcentaje de la retención no pueden ser negativos.")
    retencion.monto = calcular_retencion(
        base=retencion.base, tipo_retencion=retencion.tipo_retencion, porcentaje=retencion.porcentaje,
    )
    retencion.save()

    _sincronizar_factura_compra(retencion)
    if factura_compra_anterior is not None and factura_compra_anterior.pk != retencion.factura_compra_id:
        from apps.proveedores.core.facturas_compra_service import recalcular_retenciones_factura
        recalcular_retenciones_factura(factura_compra_anterior)

    # El asiento refleja el monto vigente: se anula el anterior y se emite uno nuevo.
    if retencion.asiento_id or retencion.factura_compra_id:
        from apps.contabilidad.services import (
            anular_asiento_si_existe, generar_asiento_automatico_retencion_proveedor,
        )
        anular_asiento_si_existe(retencion.asiento)
        retencion.asiento = (
            generar_asiento_automatico_retencion_proveedor(retencion) if retencion.factura_compra_id else None
        )
        retencion.save(update_fields=["asiento"])
    return retencion


@transaction.atomic
def anular_comprobante_retencion(retencion: Retencion) -> Retencion:
    """Baja lógica: deja de restar en la deuda con el proveedor y se anula su asiento."""
    retencion.activo = False
    retencion.save(update_fields=["activo"])
    _sincronizar_factura_compra(retencion)
    if retencion.asiento_id:
        from apps.contabilidad.services import anular_asiento_si_existe
        anular_asiento_si_existe(retencion.asiento)
    return retencion
