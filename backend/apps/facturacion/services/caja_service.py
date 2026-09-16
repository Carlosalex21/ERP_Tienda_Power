"""
Apertura y cierre de turno de caja (por USUARIO, no por terminal física --
cada vendedor abre y cierra el suyo, ver `CajaSesion`).

Mientras un turno está abierto, cada pago que ese usuario registra en el
POS (`pagos_service.procesar_pago_factura_service`) queda enlazado a él.
Al cerrar, se calcula cuánto efectivo debería haber de cada moneda
(apertura + ventas en efectivo de esa moneda durante el turno) y se compara
contra lo que el cajero contó físicamente.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum

from apps.configuracion.models import Moneda

from ..models import CajaSesion, CajaSesionMonto, Transaccionpago

CENT = Decimal("0.01")


class CajaServiceError(Exception):
    """Error controlado al abrir/cerrar un turno de caja."""


def _round(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _es_efectivo(metodo) -> bool:
    """
    Un método de pago es "efectivo" si su `tipo_metodo` lo dice así -- es
    texto libre en este sistema (no hay choices), así que se compara sin
    importar mayúsculas/acentos para no depender de cómo lo haya tecleado
    cada tenant al crear su método "Efectivo".
    """
    return bool(metodo and metodo.tipo_metodo and metodo.tipo_metodo.strip().lower() == "efectivo")


def obtener_caja_activa(usuario):
    """Devuelve el turno abierto de este usuario, o None si no tiene uno."""
    return CajaSesion.objects.filter(usuario=usuario, activo=True).prefetch_related('montos__moneda').first()


@transaction.atomic
def abrir_caja_service(usuario, montos_apertura: dict) -> CajaSesion:
    """
    Abre un turno de caja para `usuario`.

    Args:
        usuario: el cajero que abre turno.
        montos_apertura: ``{moneda_id: monto_con_el_que_arranca}`` -- puede
            traer varias monedas (ej. algo de efectivo en Bs y algo en USD).

    Raises:
        CajaServiceError: si el usuario ya tiene un turno abierto.
    """
    if CajaSesion.objects.filter(usuario=usuario, activo=True).exists():
        raise CajaServiceError("Ya tienes un turno de caja abierto. Ciérralo antes de abrir uno nuevo.")

    sesion = CajaSesion.objects.create(usuario=usuario)
    for moneda_id, monto in (montos_apertura or {}).items():
        try:
            moneda = Moneda.objects.get(id=moneda_id)
        except Moneda.DoesNotExist as exc:
            raise CajaServiceError(f"Moneda con ID {moneda_id} no existe.") from exc
        CajaSesionMonto.objects.create(caja_sesion=sesion, moneda=moneda, monto_apertura=_round(monto))

    return sesion


@transaction.atomic
def cerrar_caja_service(usuario, montos_declarados: dict, observaciones: str = "") -> CajaSesion:
    """
    Cierra el turno abierto de `usuario`.

    Para cada moneda del turno, calcula lo esperado (apertura + ventas en
    efectivo de esa moneda cobradas durante el turno -- el `vuelto` dado ya
    está descontado, porque `Transaccionpago.monto` es lo que de verdad se
    quedó en la caja, no lo que el cliente entregó) y lo compara contra lo
    declarado por el cajero.

    Args:
        usuario: el cajero que cierra turno.
        montos_declarados: ``{moneda_id: monto_contado_fisicamente}``.
        observaciones: notas libres sobre el cierre (ej. justificar una diferencia).

    Raises:
        CajaServiceError: si el usuario no tiene un turno abierto.
    """
    sesion = CajaSesion.objects.filter(usuario=usuario, activo=True).select_for_update().first()
    if sesion is None:
        raise CajaServiceError("No tienes un turno de caja abierto.")

    montos_declarados = montos_declarados or {}

    for cs_monto in sesion.montos.select_related('moneda').all():
        ventas_efectivo = Transaccionpago.objects.filter(
            caja_sesion=sesion,
            activo=True,
            estado="exitoso",
            factura__moneda=cs_monto.moneda,
        ).select_related('metodo_pago')
        total_efectivo = sum(
            (t.monto for t in ventas_efectivo if _es_efectivo(t.metodo_pago)),
            Decimal("0.00"),
        )
        cs_monto.monto_cierre_esperado = _round(cs_monto.monto_apertura + total_efectivo)

        declarado = montos_declarados.get(cs_monto.moneda_id) or montos_declarados.get(str(cs_monto.moneda_id))
        if declarado is not None:
            cs_monto.monto_cierre_declarado = _round(declarado)
        cs_monto.save(update_fields=["monto_cierre_esperado", "monto_cierre_declarado"])

    # Monedas que el cajero declaró pero que no tenían apertura registrada
    # (ej. recibió efectivo en una moneda con la que no abrió turno) --
    # igual se registran, con apertura en 0.
    ids_existentes = set(sesion.montos.values_list('moneda_id', flat=True))
    for moneda_id, declarado in montos_declarados.items():
        moneda_id_int = int(moneda_id)
        if moneda_id_int in ids_existentes:
            continue
        try:
            moneda = Moneda.objects.get(id=moneda_id_int)
        except Moneda.DoesNotExist:
            continue
        ventas_efectivo = Transaccionpago.objects.filter(
            caja_sesion=sesion, activo=True, estado="exitoso", factura__moneda=moneda,
        ).select_related('metodo_pago')
        total_efectivo = sum((t.monto for t in ventas_efectivo if _es_efectivo(t.metodo_pago)), Decimal("0.00"))
        CajaSesionMonto.objects.create(
            caja_sesion=sesion, moneda=moneda, monto_apertura=Decimal("0.00"),
            monto_cierre_esperado=_round(total_efectivo), monto_cierre_declarado=_round(declarado),
        )

    from django.utils import timezone
    sesion.fecha_cierre = timezone.now()
    sesion.observaciones_cierre = observaciones or ""
    sesion.activo = False
    sesion.save(update_fields=["fecha_cierre", "observaciones_cierre", "activo"])

    return sesion
