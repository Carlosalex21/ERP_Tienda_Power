"""
Liquidación al propietario: lo cobrado de sus alquileres, menos el honorario de la
administradora y los gastos de sus propiedades = neto a transferir.

Cada cobro y cada gasto se incluye en UNA sola liquidación (se marca al generarla);
anular la liquidación en borrador los libera para la siguiente.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.inmuebles.models import GastoPropiedad, Liquidacion, LiquidacionLinea, ReciboAplicacion
from apps.inmuebles.services.cobranza import CobranzaError, periodo_de, redondear


def _pendientes(propietario):
    aplicaciones = list(
        ReciboAplicacion.objects.select_for_update()
        .filter(
            liquidacion__isnull=True, recibo__estado='confirmado', cargo__tipo='canon',
            cargo__contrato__propietario=propietario,
        )
        .select_related('cargo__contrato', 'cargo__unidad')
        .order_by('id')
    )
    gastos = list(
        GastoPropiedad.objects.select_for_update()
        .filter(liquidacion__isnull=True, unidad__propietario=propietario).select_related('unidad').order_by('fecha', 'id')
    )
    return aplicaciones, gastos


def _armar(aplicaciones, gastos):
    """(líneas, totales) a partir de lo pendiente. Las líneas son dicts listos para guardar."""
    por_contrato: OrderedDict[int, dict] = OrderedDict()
    for a in aplicaciones:
        fila = por_contrato.setdefault(a.cargo.contrato_id, {'contrato': a.cargo.contrato, 'unidad': a.cargo.unidad, 'monto': Decimal('0')})
        fila['monto'] += a.monto_usd

    lineas = []
    total_cobrado = honorario = Decimal('0.00')
    for fila in por_contrato.values():
        cobrado = redondear(fila['monto'])
        total_cobrado += cobrado
        lineas.append({'unidad': fila['unidad'], 'tipo': 'canon', 'descripcion': f'Canon cobrado · {fila["unidad"]}', 'monto_usd': cobrado})
        pct = fila['contrato'].honorario_pct
        h = redondear(cobrado * pct / Decimal(100))
        if h > 0:
            honorario += h
            lineas.append({'unidad': fila['unidad'], 'tipo': 'honorario', 'descripcion': f'Honorario de administración {pct}% · {fila["unidad"]}', 'monto_usd': -h})

    total_gastos = Decimal('0.00')
    for g in gastos:
        total_gastos += g.monto_usd
        lineas.append({'unidad': g.unidad, 'tipo': 'gasto', 'descripcion': f'{g.descripcion} ({g.fecha:%d/%m/%Y})', 'monto_usd': -g.monto_usd})

    totales = {
        'total_cobrado_usd': redondear(total_cobrado), 'honorario_usd': redondear(honorario), 'gastos_usd': redondear(total_gastos),
        'neto_usd': redondear(total_cobrado - honorario - total_gastos),
    }
    return lineas, totales


@transaction.atomic
def previsualizar_liquidacion(propietario) -> dict:
    aplicaciones, gastos = _pendientes(propietario)
    lineas, totales = _armar(aplicaciones, gastos)
    return {
        'propietario_id': propietario.pk, 'hay_movimientos': bool(aplicaciones or gastos),
        **{k: str(v) for k, v in totales.items()},
        'lineas': [{'tipo': l['tipo'], 'descripcion': l['descripcion'], 'monto_usd': str(l['monto_usd'])} for l in lineas],
    }


@transaction.atomic
def generar_liquidacion(propietario, *, usuario, periodo: str | None = None, observaciones: str = '') -> Liquidacion:
    aplicaciones, gastos = _pendientes(propietario)
    if not aplicaciones and not gastos:
        raise CobranzaError('No hay cobros de alquiler ni gastos pendientes de liquidar a este propietario.')
    lineas, totales = _armar(aplicaciones, gastos)
    liquidacion = Liquidacion.objects.create(
        propietario=propietario, periodo=periodo or periodo_de(timezone.localdate()), observaciones=observaciones, usuario=usuario, **totales,
    )
    LiquidacionLinea.objects.bulk_create([LiquidacionLinea(liquidacion=liquidacion, **l) for l in lineas])
    ReciboAplicacion.objects.filter(pk__in=[a.pk for a in aplicaciones]).update(liquidacion=liquidacion)
    GastoPropiedad.objects.filter(pk__in=[g.pk for g in gastos]).update(liquidacion=liquidacion)
    return liquidacion


@transaction.atomic
def pagar_liquidacion(liquidacion: Liquidacion, *, fecha: date | None = None, referencia: str = '') -> Liquidacion:
    liquidacion = Liquidacion.objects.select_for_update().get(pk=liquidacion.pk)
    if liquidacion.estado != 'borrador':
        raise CobranzaError('Solo una liquidación en borrador se puede marcar como pagada.')
    liquidacion.estado = 'pagada'
    liquidacion.fecha_pago = fecha or timezone.localdate()
    liquidacion.referencia_pago = (referencia or '')[:100]
    liquidacion.save(update_fields=['estado', 'fecha_pago', 'referencia_pago'])
    return liquidacion


@transaction.atomic
def anular_liquidacion(liquidacion: Liquidacion) -> Liquidacion:
    liquidacion = Liquidacion.objects.select_for_update().get(pk=liquidacion.pk)
    if liquidacion.estado == 'pagada':
        raise CobranzaError('Esta liquidación ya se pagó al propietario; no se puede anular.')
    if liquidacion.estado == 'anulada':
        raise CobranzaError('Esta liquidación ya está anulada.')
    liquidacion.aplicaciones.update(liquidacion=None)
    liquidacion.gastos.update(liquidacion=None)
    liquidacion.estado = 'anulada'
    liquidacion.save(update_fields=['estado'])
    return liquidacion
