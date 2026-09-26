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

from ..models import CajaSesion, CajaSesionMonto, MovimientoCaja, Transaccionpago

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


def _calcular_efectivo_por_moneda(sesion, moneda):
    """Total y lista (orden cronológico) de ventas en EFECTIVO de `moneda` durante `sesion`."""
    ventas = Transaccionpago.objects.filter(
        caja_sesion=sesion, activo=True, estado="exitoso", factura__moneda=moneda,
    ).select_related('metodo_pago', 'factura').order_by('fecha')
    transacciones_efectivo = [t for t in ventas if _es_efectivo(t.metodo_pago)]
    total = sum((t.monto for t in transacciones_efectivo), Decimal("0.00"))
    return total, transacciones_efectivo


def previsualizar_cierre_caja(usuario) -> dict:
    """
    Calcula lo mismo que `cerrar_caja_service` (esperado por moneda) SIN
    cerrar el turno -- para que el cajero vea el detalle (qué ventas en
    efectivo componen ese total) ANTES de confirmar el cierre. Esto es lo
    que "justifica" la cifra final: no es un número que hay que creerle al
    sistema, se puede revisar renglón por renglón de dónde sale.
    """
    sesion = CajaSesion.objects.filter(usuario=usuario, activo=True).prefetch_related('montos__moneda').first()
    if sesion is None:
        raise CajaServiceError("No tienes un turno de caja abierto.")

    monedas = []
    for cs_monto in sesion.montos.select_related('moneda').all():
        total_efectivo, transacciones = _calcular_efectivo_por_moneda(sesion, cs_monto.moneda)
        monedas.append({
            "moneda_id": cs_monto.moneda_id,
            "moneda_codigo": cs_monto.moneda.codigo,
            "moneda_simbolo": cs_monto.moneda.simbolo,
            "monto_apertura": cs_monto.monto_apertura,
            "total_ventas_efectivo": total_efectivo,
            "monto_cierre_esperado": _round(cs_monto.monto_apertura + total_efectivo),
            "movimientos": [
                {
                    "id": t.id,
                    "fecha": t.fecha,
                    "monto": t.monto,
                    "referencia": t.referencia,
                    "factura_correlativo": t.factura.correlativo if t.factura else None,
                }
                for t in transacciones
            ],
        })
    return {"sesion_id": sesion.id, "fecha_apertura": sesion.fecha_apertura, "monedas": monedas}


def registrar_movimiento_caja(
    *, usuario, tipo: str, moneda_id, monto, concepto: str, banco_id=None, caja_sesion_id=None,
) -> MovimientoCaja:
    """
    Registra un movimiento manual de caja (ingreso/egreso) que no viene de
    cobrar una factura -- ej. "retiré el efectivo contado y lo llevé al
    banco". `caja_sesion_id` es opcional: normalmente es el turno recién
    cerrado del cajero, pero un admin puede registrar un movimiento suelto
    (ej. un ajuste) sin un turno de por medio.
    """
    if tipo not in ("ingreso", "egreso"):
        raise CajaServiceError("El tipo de movimiento debe ser 'ingreso' o 'egreso'.")
    if not moneda_id:
        raise CajaServiceError("Debes indicar la moneda del movimiento.")
    try:
        moneda = Moneda.objects.get(id=moneda_id)
    except Moneda.DoesNotExist as exc:
        raise CajaServiceError(f"Moneda con ID {moneda_id} no existe.") from exc

    banco = None
    if banco_id:
        from apps.pagos.models import Banco
        banco = Banco.objects.filter(id=banco_id).first()
        if banco is None:
            raise CajaServiceError(f"Banco con ID {banco_id} no existe.")

    caja_sesion = None
    if caja_sesion_id:
        caja_sesion = CajaSesion.objects.filter(id=caja_sesion_id).first()
        if caja_sesion is None:
            raise CajaServiceError(f"Turno de caja con ID {caja_sesion_id} no existe.")

    try:
        monto_redondeado = _round(monto)
    except Exception as exc:
        raise CajaServiceError("El monto del movimiento no es un número válido.") from exc
    if monto_redondeado <= 0:
        raise CajaServiceError("El monto del movimiento debe ser mayor a cero.")

    return MovimientoCaja.objects.create(
        tipo=tipo, caja_sesion=caja_sesion, banco=banco, moneda=moneda,
        monto=monto_redondeado, concepto=concepto or "", usuario=usuario,
    )


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
        total_efectivo, _ = _calcular_efectivo_por_moneda(sesion, cs_monto.moneda)
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
        total_efectivo, _ = _calcular_efectivo_por_moneda(sesion, moneda)
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
