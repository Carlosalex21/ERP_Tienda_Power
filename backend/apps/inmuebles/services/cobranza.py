"""
Cobranza: cargos (lo que se debe), recibos (lo que se pagó) y su aplicación.

Reglas:
- Todo se registra en USD. Un pago en bolívares guarda la tasa del día del pago,
  nunca la de hoy (así el equivalente en USD no cambia con el tiempo).
- Un recibo puede saldar varios cargos (el más antiguo primero). Lo que sobra
  queda como saldo a favor y se aplica solo a los cargos siguientes.
- Un pago ya incluido en una liquidación al propietario no se puede anular.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.inmuebles.models import Cargo, Recibo, ReciboAplicacion, Unidad

CENT = Decimal('0.01')
TIPOS_PRINCIPALES = ('cuota_condominio', 'canon', 'extraordinaria', 'multa', 'otro')


class CobranzaError(Exception):
    """Error controlado de cobranza (mensaje apto para mostrar al usuario)."""


def redondear(valor) -> Decimal:
    return Decimal(valor or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def periodo_de(fecha: date) -> str:
    return f'{fecha.year:04d}-{fecha.month:02d}'


def primer_dia(periodo: str) -> date:
    anio, mes = periodo.split('-')
    return date(int(anio), int(mes), 1)


def ultimo_dia_mes(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def fecha_en_mes(periodo: str, dia: int) -> date:
    """El día `dia` del mes `periodo` (ajustado si el mes es más corto)."""
    inicio = primer_dia(periodo)
    return date(inicio.year, inicio.month, min(dia, ultimo_dia_mes(inicio.year, inicio.month)))


def sumar_meses(periodo: str, meses: int) -> str:
    inicio = primer_dia(periodo)
    total = inicio.year * 12 + (inicio.month - 1) + meses
    return f'{total // 12:04d}-{total % 12 + 1:02d}'


# --- Moneda -------------------------------------------------------------------

def moneda_base_codigo() -> str:
    from apps.configuracion.models import Moneda
    return Moneda.objects.filter(es_predeterminada=True).values_list('codigo', flat=True).first() or 'USD'


def tasa_usd_para_fecha(fecha: date) -> Decimal:
    """Unidades de moneda base por 1 USD vigentes en `fecha` (la más reciente hasta ese día)."""
    from apps.configuracion.models import TasaCambio
    from apps.configuracion.services.conversion_service import MonedaNoEncontradaError, TasaNoDisponibleError, get_tasa_vigente

    if moneda_base_codigo() == 'USD':
        return Decimal('1')
    tasa = (
        TasaCambio.objects.filter(moneda__codigo='USD', fecha__lte=fecha, activa=True)
        .order_by('-fecha', '-id').values_list('tasa', flat=True).first()
    )
    if tasa:
        return Decimal(tasa)
    try:
        return get_tasa_vigente('USD')
    except (MonedaNoEncontradaError, TasaNoDisponibleError) as exc:
        raise CobranzaError('No hay una tasa de cambio USD cargada. Regístrala en Configuración > Tasas de cambio.') from exc


def convertir_a_usd(monto, moneda: str, *, fecha: date, tasa=None) -> tuple[Decimal, Decimal]:
    """(monto en USD, tasa usada). La tasa es "unidades de moneda base por 1 USD"."""
    monto = Decimal(monto)
    moneda = (moneda or 'USD').upper()
    base = moneda_base_codigo()
    if moneda == 'USD':
        # Pagar en dólares no necesita tasa: si hay una cargada se guarda como dato
        # informativo; si no, 1. Nunca debe impedir registrar un pago en USD.
        if tasa:
            return redondear(monto), Decimal(tasa)
        try:
            return redondear(monto), tasa_usd_para_fecha(fecha)
        except CobranzaError:
            return redondear(monto), Decimal('1')
    if moneda != base:
        raise CobranzaError(f'Solo se aceptan pagos en USD o en {base}.')
    usada = Decimal(tasa) if tasa else tasa_usd_para_fecha(fecha)
    if usada <= 0:
        raise CobranzaError('La tasa de cambio debe ser mayor a cero.')
    return redondear(monto / usada), usada


# --- Cargos -------------------------------------------------------------------

def crear_cargo(
    *, unidad: Unidad, tipo: str, concepto: str, periodo: str, monto_usd, fecha_vencimiento: date,
    fecha_emision: date | None = None, pagador=None, **extra,
) -> Cargo:
    monto = redondear(monto_usd)
    if monto <= 0:
        raise CobranzaError('El monto del cargo debe ser mayor a cero.')
    return Cargo.objects.create(
        unidad=unidad, pagador=pagador if pagador is not None else unidad.responsable_pago,
        tipo=tipo, concepto=concepto, periodo=periodo, monto_usd=monto,
        fecha_emision=fecha_emision or timezone.localdate(), fecha_vencimiento=fecha_vencimiento, **extra,
    )


@transaction.atomic
def anular_cargo(cargo: Cargo) -> Cargo:
    cargo = Cargo.objects.select_for_update().get(pk=cargo.pk)
    if cargo.estado == 'anulado':
        raise CobranzaError('Este cargo ya está anulado.')
    if cargo.monto_pagado_usd > 0:
        raise CobranzaError('Este cargo ya tiene pagos aplicados: anula primero el recibo correspondiente.')
    cargo.estado = 'anulado'
    cargo.save(update_fields=['estado'])
    return cargo


# --- Recibos ------------------------------------------------------------------

def _aplicar(recibo: Recibo, cargos) -> Decimal:
    """Aplica el crédito disponible del recibo a `cargos` (en ese orden). Devuelve lo aplicado."""
    aplicado_total = Decimal('0.00')
    for cargo in cargos:
        disponible = recibo.monto_disponible_usd - aplicado_total
        if disponible <= 0:
            break
        saldo = cargo.saldo_usd
        if saldo <= 0:
            continue
        monto = min(disponible, saldo)
        ReciboAplicacion.objects.create(recibo=recibo, cargo=cargo, monto_usd=monto)
        cargo.monto_pagado_usd = cargo.monto_pagado_usd + monto
        if cargo.saldo_usd <= 0:
            cargo.estado = 'pagado'
        cargo.save(update_fields=['monto_pagado_usd', 'estado'])
        aplicado_total += monto
    if aplicado_total:
        recibo.monto_disponible_usd = recibo.monto_disponible_usd - aplicado_total
        recibo.save(update_fields=['monto_disponible_usd'])
    return aplicado_total


def _pendientes(unidad: Unidad):
    return list(
        Cargo.objects.select_for_update().filter(unidad=unidad, estado='pendiente').order_by('fecha_vencimiento', 'id')
    )


@transaction.atomic
def registrar_recibo(
    *, usuario, unidad: Unidad, fecha: date, monto_pago, moneda_pago: str = 'USD', tasa=None,
    metodo: str = 'transferencia', referencia: str = '', banco: str = '', pagador=None,
    cargos=None, comprobante=None, observaciones: str = '',
) -> Recibo:
    """
    Registra un pago de una unidad y lo aplica a sus deudas: a los `cargos` indicados
    (en ese orden) o, si no se indican, a los más antiguos primero.
    """
    monto_pago = Decimal(monto_pago)
    if monto_pago <= 0:
        raise CobranzaError('El monto pagado debe ser mayor a cero.')
    if fecha > timezone.localdate():
        raise CobranzaError('La fecha del pago no puede ser futura.')
    referencia = (referencia or '').strip()
    unidad = Unidad.objects.select_for_update().get(pk=unidad.pk)

    if referencia and Recibo.objects.filter(
        unidad=unidad, referencia=referencia, monto_pago=monto_pago, fecha=fecha, estado='confirmado',
    ).exists():
        raise CobranzaError(f'Ya registraste un pago con la referencia {referencia} por ese monto y fecha.')

    monto_usd, tasa_usada = convertir_a_usd(monto_pago, moneda_pago, fecha=fecha, tasa=tasa)
    if monto_usd <= 0:
        raise CobranzaError('El pago es demasiado pequeño para registrarse.')

    recibo = Recibo.objects.create(
        unidad=unidad, pagador=pagador if pagador is not None else unidad.responsable_pago, fecha=fecha,
        metodo=metodo, referencia=referencia, banco=banco, moneda_pago=(moneda_pago or 'USD').upper(),
        monto_pago=monto_pago, tasa=tasa_usada, monto_usd=monto_usd, monto_disponible_usd=monto_usd,
        comprobante=comprobante, observaciones=observaciones, usuario=usuario,
    )

    if cargos:
        elegidos = list(Cargo.objects.select_for_update().filter(pk__in=[c.pk for c in cargos]))
        por_id = {c.pk: c for c in elegidos}
        ordenados = []
        for c in cargos:
            actual = por_id.get(c.pk)
            if actual is None or actual.unidad_id != unidad.pk:
                raise CobranzaError('Una de las deudas indicadas no pertenece a esta unidad.')
            if actual.estado != 'pendiente':
                raise CobranzaError(f'La deuda "{actual.concepto}" ya no está pendiente.')
            ordenados.append(actual)
        _aplicar(recibo, ordenados)
    else:
        _aplicar(recibo, _pendientes(unidad))
    return recibo


@transaction.atomic
def anular_recibo(recibo: Recibo, *, motivo: str = '') -> Recibo:
    recibo = Recibo.objects.select_for_update().get(pk=recibo.pk)
    if recibo.estado == 'anulado':
        raise CobranzaError('Este recibo ya está anulado.')
    aplicaciones = list(recibo.aplicaciones.select_related('cargo'))
    if any(a.liquidacion_id for a in aplicaciones):
        raise CobranzaError('Este cobro ya se incluyó en una liquidación al propietario: anula primero esa liquidación.')

    for aplicacion in aplicaciones:
        cargo = Cargo.objects.select_for_update().get(pk=aplicacion.cargo_id)
        cargo.monto_pagado_usd = cargo.monto_pagado_usd - aplicacion.monto_usd
        if cargo.estado == 'pagado' and cargo.saldo_usd > 0:
            cargo.estado = 'pendiente'
        cargo.save(update_fields=['monto_pagado_usd', 'estado'])
    recibo.aplicaciones.all().delete()

    recibo.estado = 'anulado'
    recibo.monto_disponible_usd = Decimal('0.00')
    recibo.fecha_anulacion = timezone.now()
    recibo.motivo_anulacion = (motivo or '')[:255]
    recibo.save(update_fields=['estado', 'monto_disponible_usd', 'fecha_anulacion', 'motivo_anulacion'])
    return recibo


@transaction.atomic
def aplicar_creditos(unidad: Unidad) -> Decimal:
    """Aplica el saldo a favor de la unidad (pagos que sobraron) a sus deudas pendientes."""
    total = Decimal('0.00')
    recibos = Recibo.objects.select_for_update().filter(
        unidad=unidad, estado='confirmado', monto_disponible_usd__gt=0,
    ).order_by('fecha', 'id')
    for recibo in recibos:
        pendientes = _pendientes(unidad)
        if not pendientes:
            break
        total += _aplicar(recibo, pendientes)
    return total


# --- Mora ---------------------------------------------------------------------

def _mora_de(cargo: Cargo) -> tuple[Decimal, int]:
    if cargo.contrato_id:
        return cargo.contrato.mora_pct_mensual, cargo.contrato.dias_gracia
    edificio = cargo.unidad.edificio
    if edificio is not None:
        return edificio.mora_pct_mensual, edificio.dias_gracia
    return Decimal('0'), 0


def aplicar_mora(hoy: date | None = None) -> int:
    """
    Genera, una vez por mes y por deuda vencida, un cargo de mora = % mensual del
    saldo pendiente de esa deuda. Idempotente (la restricción única impide duplicar).
    Devuelve cuántas moras se crearon.
    """
    hoy = hoy or timezone.localdate()
    periodo = periodo_de(hoy)
    creadas = 0
    vencidos = Cargo.objects.filter(
        estado='pendiente', tipo__in=TIPOS_PRINCIPALES, fecha_vencimiento__lt=hoy,
    ).select_related('unidad__edificio', 'contrato')
    for cargo in vencidos:
        pct, gracia = _mora_de(cargo)
        if not pct or pct <= 0:
            continue
        if cargo.fecha_vencimiento + timedelta(days=gracia) >= hoy:
            continue
        monto = redondear(cargo.saldo_usd * pct / Decimal(100))
        if monto <= 0:
            continue
        try:
            with transaction.atomic():
                crear_cargo(
                    unidad=cargo.unidad, tipo='mora', concepto=f'Mora {periodo} · {cargo.concepto}', periodo=periodo,
                    monto_usd=monto, fecha_vencimiento=hoy, fecha_emision=hoy, pagador=cargo.pagador, cargo_origen=cargo,
                    contrato=None,
                )
                creadas += 1
        except IntegrityError:
            continue  # ya tenía la mora de este mes
    return creadas


# --- Consultas ----------------------------------------------------------------

def saldo_pendiente_unidad(unidad: Unidad, *, solo_vencido: bool = False, hoy: date | None = None) -> Decimal:
    cargos = Cargo.objects.filter(unidad=unidad, estado='pendiente')
    if solo_vencido:
        cargos = cargos.filter(fecha_vencimiento__lt=hoy or timezone.localdate())
    pendiente = sum((c.saldo_usd for c in cargos), Decimal('0.00'))
    return redondear(pendiente)


def saldo_a_favor_unidad(unidad: Unidad) -> Decimal:
    total = Recibo.objects.filter(unidad=unidad, estado='confirmado').aggregate(t=Sum('monto_disponible_usd'))['t']
    return redondear(total)
