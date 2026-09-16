"""
Lógica de negocio de las Notas de Crédito y Notas de Débito (SENIAT).

Una nota de crédito reduce el débito fiscal del emisor (devolución/anulación
parcial o total de una factura). Una nota de débito lo incrementa (recargos,
intereses, diferencias de cambio).

Cada nota se registra automáticamente en el Libro de Venta con el monto
correspondiente y se genera su número de control SENIAT.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction



from apps.configuracion.core.config_service import (
    obtener_y_actualizar_numero_control_nota_credito,
    obtener_y_actualizar_numero_control_nota_debito,
)

from apps.facturacion.models import Factura, NotaCredito, NotaDebito

from .libros_service import registrar_en_libro_compra_venta

CENT = Decimal("0.01")


class NotaServiceError(Exception):
    """Error controlado durante la creación de notas de crédito/débito."""


def _round(value: Decimal) -> Decimal:
    """Redondea a 2 decimales con redondeo bancario."""
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)




def _proporcionar(factura: Factura, monto: Decimal) -> dict[str, Decimal]:
    """
    Calcula la distribución proporcional de base, IVA y retención de una nota.

    El monto de la nota es una fracción del total de la factura; se aplica esa
    misma proporción a la base, IVA y retención para no distorsionar el
    desglose fiscal. `monto` se interpreta en la MISMA moneda que la propia
    factura (igual que `factura.total`) -- así que la nota (`NotaCredito`/
    `NotaDebito`) queda, a propósito, en esa misma moneda: es "una porción
    de esta factura", tiene sentido mostrarla en los mismos términos que
    ella. Los `_base` de este dict son la misma proporción aplicada a los
    montos YA convertidos a la moneda base de la factura -- se usan solo
    para registrar la nota en el Libro Fiscal (ver `registrar_en_libro_compra_venta`
    en los llamadores), que no distingue moneda por fila y por lo tanto
    nunca debe recibir un monto crudo de una factura en moneda extranjera.

    Args:
        factura: Factura origen.
        monto: Monto de la nota, en la moneda de la factura (positivo).

    Returns:
        dict: ``{base_imponible, iva, retencion, total, base_imponible_base, iva_base, retencion_base, total_base}``.
    """
    monto = _round(monto)
    total_factura = factura.total or Decimal("0.00")
    if total_factura <= 0:
        raise NotaServiceError("La factura no tiene un total válido para emitir notas.")

    proporcion = monto / total_factura
    return {
        "base_imponible": _round(factura.base_imponible * proporcion),
        "iva": _round(factura.iva_total * proporcion),
        "retencion": _round(factura.retencion_total * proporcion),
        "total": monto,
        "base_imponible_base": _round(factura.base_imponible_base * proporcion),
        "iva_base": _round(factura.iva_base * proporcion),
        "retencion_base": _round(factura.retencion_base * proporcion),
        "total_base": _round(factura.total_base * proporcion),
    }


@transaction.atomic
def crear_nota_credito(factura_id: int, monto: Decimal, motivo: str) -> NotaCredito:
    """
    Crea una nota de crédito asociada a una factura.

    Args:
        factura_id: ID de la factura origen.
        monto: Monto acreditar (<= factura.total).
        motivo: Justificación de la emisión.

    Returns:
        NotaCredito: La nota creada.

    Raises:
        NotaServiceError: Si la factura no existe, el monto excede el total,
            la factura está anulada o la nota duplica el total acreditado.
    """
    try:
        factura = Factura.objects.select_for_update().get(pk=factura_id)
    except Factura.DoesNotExist as exc:
        raise NotaServiceError("La factura asociada no existe.") from exc

    if factura.estado == "anulada":
        raise NotaServiceError("No se puede emitir una nota de crédito sobre una factura anulada.")

    monto = _round(monto)
    if monto <= 0:
        raise NotaServiceError("El monto de la nota de crédito debe ser mayor que cero.")
    if monto > factura.total:
        raise NotaServiceError(
            f"El monto ({monto}) no puede exceder el total de la factura ({factura.total})."
        )

    # Evita superar el total ya acreditado por notas previas.
    total_acreditado = sum(
        (nc.total or Decimal("0.00")) for nc in
        NotaCredito.objects.filter(factura=factura, activo=True)
    )
    if (total_acreditado + monto) > factura.total + Decimal("0.01"):
        raise NotaServiceError(
            "La suma de notas de crédito no puede exceder el total de la factura."
        )

    distribuido = _proporcionar(factura, monto)
    # Secuencia propia de Nota de Crédito -- antes usaba la misma que las
    # facturas (`obtener_y_actualizar_numero_control`), así que cada nota
    # emitida "robaba" un número de la numeración de facturas en vez de
    # llevar su propia serie correlativa, como exige el SENIAT.
    numero_control = obtener_y_actualizar_numero_control_nota_credito()

    nota = NotaCredito.objects.create(
        factura=factura,
        numero_nota=numero_control,  # Se reutiliza el número de control como identificador.
        numero_control=numero_control,
        motivo=motivo,
        base_imponible=distribuido["base_imponible"],
        iva_total=distribuido["iva"],
        retencion_total=distribuido["retencion"],
        total=monto,
        base_imponible_base=distribuido["base_imponible_base"],
        iva_base=distribuido["iva_base"],
        retencion_base=distribuido["retencion_base"],
        total_base=distribuido["total_base"],
    )

    # Registro en el Libro de Venta (monto negativo = resta el débito fiscal).
    registrar_en_libro_compra_venta(
        tipo_libro="venta",
        fecha_operacion=factura.fecha_operacion.date(),
        tipo_documento="Nota de Crédito",
        numero_documento=nota.numero_nota,
        numero_control=nota.numero_control,
        rif=factura.cliente.documento if factura.cliente else None,
        razon_social=factura.cliente.nombre if factura.cliente else "Consumidor Final",
        base_imponible=-distribuido["base_imponible_base"],
        iva=-distribuido["iva_base"],
        retencion=-distribuido["retencion_base"],
        total=-distribuido["total_base"],
    )

    return nota


@transaction.atomic
def crear_nota_debito(factura_id: int, monto: Decimal, motivo: str) -> NotaDebito:
    """
    Crea una nota de débito asociada a una factura.

    Args:
        factura_id: ID de la factura origen.
        monto: Monto a debitar (recargo, interés, diferencia).
        motivo: Justificación de la emisión.

    Returns:
        NotaDebito: La nota creada.

    Raises:
        NotaServiceError: Si la factura no existe, está anulada o el monto es
            inválido.
    """
    try:
        factura = Factura.objects.select_for_update().get(pk=factura_id)
    except Factura.DoesNotExist as exc:
        raise NotaServiceError("La factura asociada no existe.") from exc

    if factura.estado == "anulada":
        raise NotaServiceError("No se puede emitir una nota de débito sobre una factura anulada.")

    monto = _round(monto)
    if monto <= 0:
        raise NotaServiceError("El monto de la nota de débito debe ser mayor que cero.")

    distribuido = _proporcionar(factura, monto)
    # Ver el mismo comentario en `crear_nota_credito`.
    numero_control = obtener_y_actualizar_numero_control_nota_debito()

    nota = NotaDebito.objects.create(
        factura=factura,
        numero_nota=numero_control,
        numero_control=numero_control,
        motivo=motivo,
        base_imponible=distribuido["base_imponible"],
        iva_total=distribuido["iva"],
        total=monto,
        base_imponible_base=distribuido["base_imponible_base"],
        iva_base=distribuido["iva_base"],
        total_base=distribuido["total_base"],
    )

    # Registro en el Libro de Venta (monto positivo = incrementa débito fiscal).
    registrar_en_libro_compra_venta(
        tipo_libro="venta",
        fecha_operacion=factura.fecha_operacion.date(),
        tipo_documento="Nota de Débito",
        numero_documento=nota.numero_nota,
        numero_control=nota.numero_control,
        rif=factura.cliente.documento if factura.cliente else None,
        razon_social=factura.cliente.nombre if factura.cliente else "Consumidor Final",
        base_imponible=distribuido["base_imponible_base"],
        iva=distribuido["iva_base"],
        retencion=Decimal("0.00"),
        total=distribuido["total_base"],
    )

    return nota
