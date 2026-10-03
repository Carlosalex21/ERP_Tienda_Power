"""
Contratos de arrendamiento: alta, activación, cargos mensuales del canon,
renovación y rescisión.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.inmuebles.models import Cargo, Contrato, Unidad
from apps.inmuebles.services.cobranza import (
    CobranzaError, anular_cargo, crear_cargo, fecha_en_mes, periodo_de, redondear, sumar_meses,
)


def _validar_fechas(inicio: date, fin: date) -> None:
    if fin <= inicio:
        raise CobranzaError('La fecha de fin del contrato debe ser posterior a la de inicio.')


@transaction.atomic
def crear_contrato(
    *, usuario, unidad: Unidad, inquilino, fecha_inicio: date, fecha_fin: date, canon_usd, dia_pago: int = 5,
    deposito_usd=0, honorario_pct=0, ajuste_anual_pct=0, mora_pct_mensual=0, dias_gracia: int = 0,
    documento=None, observaciones: str = '', contrato_anterior: Contrato | None = None,
) -> Contrato:
    _validar_fechas(fecha_inicio, fecha_fin)
    if not unidad.activo:
        raise CobranzaError('La propiedad está desactivada.')
    if redondear(canon_usd) <= 0:
        raise CobranzaError('El canon debe ser mayor a cero.')
    return Contrato.objects.create(
        unidad=unidad, inquilino=inquilino, propietario=unidad.propietario, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
        canon_usd=redondear(canon_usd), dia_pago=dia_pago, deposito_usd=redondear(deposito_usd), honorario_pct=honorario_pct,
        ajuste_anual_pct=ajuste_anual_pct, mora_pct_mensual=mora_pct_mensual, dias_gracia=dias_gracia, documento=documento,
        observaciones=observaciones, contrato_anterior=contrato_anterior, usuario=usuario,
    )


def canon_del_periodo(contrato: Contrato, periodo: str) -> Decimal:
    """Canon del mes: el pactado, con el aumento anual aplicado por cada año de contrato transcurrido."""
    inicio = contrato.fecha_inicio
    anio, mes = (int(x) for x in periodo.split('-'))
    meses = (anio - inicio.year) * 12 + (mes - inicio.month)
    anios = max(meses // 12, 0)
    factor = (Decimal(1) + Decimal(contrato.ajuste_anual_pct) / Decimal(100)) ** anios
    return redondear(contrato.canon_usd * factor)


def generar_cargos_contrato(contrato: Contrato, hasta_periodo: str | None = None) -> int:
    """
    Crea los cargos de canon que falten, mes por mes, desde el mes de inicio (o desde el de
    la creación del contrato, si empezó en el pasado: lo anterior se carga a mano) hasta
    `hasta_periodo` (el mes actual por defecto) o el fin del contrato. Idempotente.
    """
    if contrato.estado != 'vigente':
        return 0
    hoy = timezone.localdate()
    hasta = hasta_periodo or periodo_de(hoy)
    primero = periodo_de(max(contrato.fecha_inicio, contrato.fecha_creacion.date()))
    ultimo = min(hasta, periodo_de(contrato.fecha_fin))
    creados = 0
    periodo = primero
    while periodo <= ultimo:
        if not Cargo.objects.filter(contrato=contrato, tipo='canon', periodo=periodo).exclude(estado='anulado').exists():
            try:
                with transaction.atomic():
                    crear_cargo(
                        unidad=contrato.unidad, tipo='canon', concepto=f'Canon de alquiler {periodo}', periodo=periodo,
                        monto_usd=canon_del_periodo(contrato, periodo), fecha_vencimiento=fecha_en_mes(periodo, contrato.dia_pago),
                        fecha_emision=min(hoy, fecha_en_mes(periodo, contrato.dia_pago)), pagador=contrato.inquilino, contrato=contrato,
                    )
                    creados += 1
            except IntegrityError:
                pass
        periodo = sumar_meses(periodo, 1)
    return creados


@transaction.atomic
def activar_contrato(contrato: Contrato, *, cobrar_deposito: bool = True) -> Contrato:
    contrato = Contrato.objects.select_for_update().get(pk=contrato.pk)
    if contrato.estado != 'borrador':
        raise CobranzaError('Solo un contrato en borrador se puede activar.')
    unidad = Unidad.objects.select_for_update().get(pk=contrato.unidad_id)
    solapado = Contrato.objects.filter(
        unidad=unidad, estado='vigente', fecha_inicio__lte=contrato.fecha_fin, fecha_fin__gte=contrato.fecha_inicio,
    ).exclude(pk=contrato.pk).first()
    if solapado:
        raise CobranzaError(
            f'La propiedad ya tiene un contrato vigente que se solapa ({solapado.fecha_inicio:%d/%m/%Y} a {solapado.fecha_fin:%d/%m/%Y}).'
        )

    contrato.estado = 'vigente'
    contrato.propietario = contrato.propietario or unidad.propietario
    contrato.save(update_fields=['estado', 'propietario'])

    unidad.estado = 'ocupada'
    unidad.ocupante = contrato.inquilino
    unidad.publicada = False
    unidad.save(update_fields=['estado', 'ocupante', 'publicada'])

    if cobrar_deposito and contrato.deposito_usd > 0 and contrato.contrato_anterior_id is None:
        hoy = timezone.localdate()
        crear_cargo(
            unidad=unidad, tipo='deposito', concepto='Depósito en garantía', periodo=periodo_de(max(contrato.fecha_inicio, hoy)),
            monto_usd=contrato.deposito_usd, fecha_vencimiento=max(contrato.fecha_inicio, hoy), pagador=contrato.inquilino,
        )
    generar_cargos_contrato(contrato)
    return contrato


@transaction.atomic
def rescindir_contrato(contrato: Contrato, *, fecha: date | None = None, motivo: str = '') -> Contrato:
    contrato = Contrato.objects.select_for_update().get(pk=contrato.pk)
    if contrato.estado != 'vigente':
        raise CobranzaError('Solo se puede rescindir un contrato vigente.')
    fecha = fecha or timezone.localdate()
    contrato.estado = 'rescindido'
    contrato.fecha_rescision = fecha
    contrato.motivo_rescision = (motivo or '')[:255]
    contrato.save(update_fields=['estado', 'fecha_rescision', 'motivo_rescision'])

    # Los cánones de meses posteriores a la rescisión que nadie ha pagado ya no se deben.
    for cargo in Cargo.objects.filter(contrato=contrato, tipo='canon', estado='pendiente', periodo__gt=periodo_de(fecha), monto_pagado_usd=0):
        anular_cargo(cargo)

    unidad = Unidad.objects.select_for_update().get(pk=contrato.unidad_id)
    unidad.estado = 'disponible'
    unidad.ocupante = None
    unidad.save(update_fields=['estado', 'ocupante'])
    return contrato


@transaction.atomic
def renovar_contrato(contrato: Contrato, *, usuario, nueva_fecha_fin: date, nuevo_canon=None) -> Contrato:
    """Crea y activa el contrato siguiente (arranca el día después de que termina el actual)."""
    if contrato.estado not in ('vigente', 'vencido'):
        raise CobranzaError('Solo se puede renovar un contrato vigente o vencido.')
    nuevo_inicio = contrato.fecha_fin + timedelta(days=1)
    nuevo = crear_contrato(
        usuario=usuario, unidad=contrato.unidad, inquilino=contrato.inquilino, fecha_inicio=nuevo_inicio, fecha_fin=nueva_fecha_fin,
        canon_usd=nuevo_canon if nuevo_canon is not None else contrato.canon_usd, dia_pago=contrato.dia_pago,
        deposito_usd=contrato.deposito_usd, honorario_pct=contrato.honorario_pct, ajuste_anual_pct=contrato.ajuste_anual_pct,
        mora_pct_mensual=contrato.mora_pct_mensual, dias_gracia=contrato.dias_gracia, contrato_anterior=contrato,
        observaciones=f'Renovación del contrato {contrato.pk}.',
    )
    return activar_contrato(nuevo, cobrar_deposito=False)


def procesar_contratos(hoy: date | None = None) -> dict:
    """Tarea diaria: vence los contratos terminados y genera los cánones del mes de los vigentes."""
    hoy = hoy or timezone.localdate()
    vencidos = Contrato.objects.filter(estado='vigente', fecha_fin__lt=hoy).update(estado='vencido')
    creados = 0
    for contrato in Contrato.objects.filter(estado='vigente').select_related('unidad', 'inquilino'):
        creados += generar_cargos_contrato(contrato)
    return {'vencidos': vencidos, 'cargos_creados': creados}
