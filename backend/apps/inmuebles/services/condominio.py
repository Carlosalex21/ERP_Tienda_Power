"""
Condominios: distribución de los gastos comunes entre las unidades según su
alícuota y emisión de las cuotas de cada mes.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.inmuebles.models import Cargo, Edificio, GastoComun, PeriodoCondominio, Unidad, validar_periodo
from apps.inmuebles.services.cobranza import (
    CobranzaError, aplicar_creditos, crear_cargo, fecha_en_mes, periodo_de, redondear, sumar_meses,
)

TOLERANCIA_ALICUOTAS = Decimal('0.01')


def _validar(periodo: str) -> None:
    try:
        validar_periodo(periodo)
    except Exception as exc:
        raise CobranzaError('El período debe tener el formato AAAA-MM (ej. 2026-10).') from exc


def periodo_emitido(edificio: Edificio, periodo: str) -> PeriodoCondominio | None:
    return PeriodoCondominio.objects.filter(edificio=edificio, periodo=periodo).exclude(estado='anulado').first()


def validar_gasto_editable(edificio: Edificio, periodo: str) -> None:
    """Un mes ya emitido no admite gastos nuevos ni cambios: ya se cobró a los vecinos."""
    if periodo_emitido(edificio, periodo):
        raise CobranzaError(
            f'El período {periodo} de {edificio.nombre} ya fue emitido. Para corregirlo, anula el período '
            'o carga el ajuste como cuota extraordinaria.'
        )


def vencimiento_por_defecto(edificio: Edificio, emision: date) -> date:
    candidato = fecha_en_mes(periodo_de(emision), edificio.dia_vencimiento)
    if candidato <= emision:
        candidato = fecha_en_mes(sumar_meses(periodo_de(emision), 1), edificio.dia_vencimiento)
    return candidato


def _distribuir(total: Decimal, unidades: list[Unidad]) -> dict[int, Decimal]:
    """Reparte `total` proporcional a la alícuota; los centavos de redondeo van a la unidad mayor."""
    suma = sum((u.alicuota for u in unidades), Decimal('0'))
    if not unidades or suma <= 0:
        return {}
    montos = {u.pk: redondear(total * u.alicuota / suma) for u in unidades}
    diferencia = redondear(total - sum(montos.values(), Decimal('0')))
    if diferencia != 0:
        mayor = max(unidades, key=lambda u: (u.alicuota, -u.pk))
        montos[mayor.pk] = redondear(montos[mayor.pk] + diferencia)
    return montos


def previsualizar_periodo(edificio: Edificio, periodo: str) -> dict:
    """Cómo quedaría la distribución si se emitiera hoy (no escribe nada)."""
    _validar(periodo)
    gastos = GastoComun.objects.filter(edificio=edificio, periodo=periodo)
    total_gastos = redondear(gastos.aggregate(t=Sum('monto_usd'))['t'])
    fondo = redondear(total_gastos * edificio.fondo_reserva_pct / Decimal(100))
    a_distribuir = redondear(total_gastos + fondo)

    unidades = list(
        Unidad.objects.filter(edificio=edificio, activo=True, alicuota__gt=0).select_related('propietario', 'ocupante')
    )
    sin_alicuota = Unidad.objects.filter(edificio=edificio, activo=True, alicuota=0).count()
    suma = sum((u.alicuota for u in unidades), Decimal('0'))
    montos = _distribuir(a_distribuir, unidades)

    advertencias = []
    if total_gastos <= 0:
        advertencias.append('Este mes no tiene gastos cargados.')
    if not unidades:
        advertencias.append('El edificio no tiene unidades con alícuota.')
    elif abs(suma - Decimal(100)) > TOLERANCIA_ALICUOTAS:
        advertencias.append(f'Las alícuotas suman {suma:.4f}% y deben sumar 100%.')
    if sin_alicuota:
        advertencias.append(f'{sin_alicuota} unidad(es) activas tienen alícuota 0 y no recibirán cuota.')
    sin_responsable = [u.codigo for u in unidades if u.responsable_pago is None]
    if sin_responsable:
        advertencias.append('Sin propietario registrado: ' + ', '.join(sin_responsable[:10]) + ('…' if len(sin_responsable) > 10 else ''))

    existente = periodo_emitido(edificio, periodo)
    return {
        'edificio_id': edificio.pk,
        'periodo': periodo,
        'ya_emitido': existente is not None,
        'gastos_cantidad': gastos.count(),
        'total_gastos_usd': str(total_gastos),
        'fondo_reserva_usd': str(fondo),
        'total_a_distribuir_usd': str(a_distribuir),
        'suma_alicuotas': str(suma),
        'alicuotas_completas': abs(suma - Decimal(100)) <= TOLERANCIA_ALICUOTAS,
        'vencimiento_sugerido': vencimiento_por_defecto(edificio, timezone.localdate()).isoformat(),
        'unidades': [
            {
                'unidad_id': u.pk, 'codigo': u.codigo, 'alicuota': str(u.alicuota),
                'responsable': u.responsable_pago.nombre if u.responsable_pago else None,
                'monto_usd': str(montos.get(u.pk, Decimal('0.00'))),
            }
            for u in unidades
        ],
        'advertencias': advertencias,
    }


@transaction.atomic
def emitir_periodo(
    edificio: Edificio, periodo: str, *, usuario, fecha_vencimiento: date | None = None, forzar_alicuotas: bool = False,
) -> PeriodoCondominio:
    """Crea la cuota de cada unidad. Un mes ya emitido no se vuelve a emitir."""
    _validar(periodo)
    edificio = Edificio.objects.select_for_update().get(pk=edificio.pk)
    if periodo_emitido(edificio, periodo):
        raise CobranzaError(f'El período {periodo} de {edificio.nombre} ya fue emitido.')

    vista = previsualizar_periodo(edificio, periodo)
    total_gastos = Decimal(vista['total_gastos_usd'])
    if total_gastos <= 0:
        raise CobranzaError('Carga al menos un gasto del mes antes de emitir.')
    if not vista['unidades']:
        raise CobranzaError('El edificio no tiene unidades con alícuota para repartir.')
    if not vista['alicuotas_completas'] and not forzar_alicuotas:
        raise CobranzaError(
            f'Las alícuotas de las unidades suman {vista["suma_alicuotas"]}% y deben sumar 100%. '
            'Corrígelas, o emite igualmente repartiendo en proporción a las que hay.'
        )

    hoy = timezone.localdate()
    vencimiento = fecha_vencimiento or vencimiento_por_defecto(edificio, hoy)

    fondo = Decimal(vista['fondo_reserva_usd'])
    a_distribuir = Decimal(vista['total_a_distribuir_usd'])
    periodo_obj = PeriodoCondominio.objects.create(
        edificio=edificio, periodo=periodo, total_gastos_usd=total_gastos, fondo_reserva_usd=fondo,
        total_distribuido_usd=a_distribuir, fecha_emision=hoy, fecha_vencimiento=vencimiento, emitido_por=usuario,
    )
    unidades = {u.pk: u for u in Unidad.objects.filter(pk__in=[f['unidad_id'] for f in vista['unidades']]).select_related('propietario', 'ocupante')}
    for fila in vista['unidades']:
        unidad = unidades[fila['unidad_id']]
        monto = Decimal(fila['monto_usd'])
        if monto <= 0:
            continue
        crear_cargo(
            unidad=unidad, tipo='cuota_condominio', concepto=f'Cuota de condominio {periodo}', periodo=periodo,
            monto_usd=monto, fecha_vencimiento=vencimiento, fecha_emision=hoy, periodo_condominio=periodo_obj,
            monto_fondo_usd=redondear(monto * fondo / a_distribuir) if a_distribuir else 0,
        )
        aplicar_creditos(unidad)
    return periodo_obj


@transaction.atomic
def anular_periodo(periodo_obj: PeriodoCondominio) -> PeriodoCondominio:
    periodo_obj = PeriodoCondominio.objects.select_for_update().get(pk=periodo_obj.pk)
    if periodo_obj.estado == 'anulado':
        raise CobranzaError('Este período ya está anulado.')
    cargos = list(periodo_obj.cargos.select_for_update().exclude(estado='anulado'))
    if any(c.monto_pagado_usd > 0 for c in cargos):
        raise CobranzaError('Hay cuotas de este período con pagos aplicados: anula primero esos recibos.')
    for cargo in cargos:
        cargo.estado = 'anulado'
        cargo.save(update_fields=['estado'])
    periodo_obj.estado = 'anulado'
    periodo_obj.save(update_fields=['estado'])
    return periodo_obj
