"""Reportes: morosidad, estado de cuenta, solvencia, tablero y recordatorios."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.inmuebles.models import Cargo, Contrato, ConsultaPropiedad, PagoReportado, Recibo, Unidad
from apps.inmuebles.services.cobranza import periodo_de, primer_dia, redondear, saldo_a_favor_unidad

BUCKETS = ('0_30', '31_60', '61_90', 'mas_90')


def _bucket(dias: int) -> str:
    return '0_30' if dias <= 30 else '31_60' if dias <= 60 else '61_90' if dias <= 90 else 'mas_90'


def reporte_morosidad(*, fecha_corte: date | None = None, edificio_id: int | None = None) -> dict:
    """
    Unidades con deuda vencida a `fecha_corte`, con antigüedad por tramos (días de atraso)
    y datos para contactarlas. El resumen incluye el total y el % de unidades morosas.
    """
    fecha_corte = fecha_corte or timezone.localdate()
    cargos = (
        Cargo.objects.filter(estado='pendiente', fecha_vencimiento__lt=fecha_corte)
        .select_related('unidad__edificio', 'unidad__propietario', 'unidad__ocupante', 'pagador')
        .order_by('fecha_vencimiento', 'id')
    )
    if edificio_id:
        cargos = cargos.filter(unidad__edificio_id=edificio_id)

    filas: dict[int, dict] = {}
    for cargo in cargos:
        saldo = cargo.saldo_usd
        if saldo <= 0:
            continue
        unidad = cargo.unidad
        responsable = cargo.pagador or unidad.responsable_pago
        fila = filas.setdefault(unidad.pk, {
            'unidad_id': unidad.pk, 'unidad': unidad.codigo,
            'edificio_id': unidad.edificio_id, 'edificio': unidad.edificio.nombre if unidad.edificio_id else '',
            'responsable_id': responsable.pk if responsable else None,
            'responsable': responsable.nombre if responsable else 'Sin responsable',
            'telefono': responsable.telefono if responsable else None,
            'total_vencido_usd': Decimal('0.00'), **{b: Decimal('0.00') for b in BUCKETS},
            'periodos': set(), 'deuda_mas_antigua': cargo.fecha_vencimiento, 'cargos': 0,
        })
        dias = (fecha_corte - cargo.fecha_vencimiento).days
        fila['total_vencido_usd'] += saldo
        fila[_bucket(dias)] += saldo
        fila['periodos'].add(cargo.periodo)
        fila['cargos'] += 1

    resultado = []
    for fila in filas.values():
        fila['meses_vencidos'] = len(fila.pop('periodos'))
        fila['dias_atraso'] = (fecha_corte - fila['deuda_mas_antigua']).days
        fila['deuda_mas_antigua'] = fila['deuda_mas_antigua'].isoformat()
        for campo in ('total_vencido_usd', *BUCKETS):
            fila[campo] = str(redondear(fila[campo]))
        resultado.append(fila)
    resultado.sort(key=lambda f: Decimal(f['total_vencido_usd']), reverse=True)

    unidades = Unidad.objects.filter(activo=True)
    if edificio_id:
        unidades = unidades.filter(edificio_id=edificio_id)
    total_unidades = unidades.count()
    total_vencido = sum((Decimal(f['total_vencido_usd']) for f in resultado), Decimal('0.00'))
    return {
        'fecha_corte': fecha_corte.isoformat(),
        'resumen': {
            'unidades_morosas': len(resultado),
            'total_unidades': total_unidades,
            'porcentaje_morosidad': str(redondear(Decimal(len(resultado)) * 100 / total_unidades)) if total_unidades else '0.00',
            'total_vencido_usd': str(redondear(total_vencido)),
        },
        'filas': resultado,
    }


def estado_cuenta(unidad: Unidad, *, hasta: date | None = None) -> dict:
    """Movimientos de la unidad en orden cronológico con saldo acumulado (positivo = debe)."""
    hasta = hasta or timezone.localdate()
    movimientos = []
    for c in Cargo.objects.filter(unidad=unidad).exclude(estado='anulado').filter(fecha_emision__lte=hasta):
        movimientos.append({
            'fecha': c.fecha_emision, 'orden': 0, 'tipo': 'cargo', 'concepto': c.concepto, 'periodo': c.periodo,
            'debe': c.monto_usd, 'haber': Decimal('0.00'), 'vencimiento': c.fecha_vencimiento, 'referencia': f'C-{c.pk}',
        })
    for r in Recibo.objects.filter(unidad=unidad, estado='confirmado', fecha__lte=hasta):
        movimientos.append({
            'fecha': r.fecha, 'orden': 1, 'tipo': 'pago', 'concepto': f'Pago {r.numero} ({r.get_metodo_display()})', 'periodo': '',
            'debe': Decimal('0.00'), 'haber': r.monto_usd, 'vencimiento': None, 'referencia': r.numero,
        })
    movimientos.sort(key=lambda m: (m['fecha'], m['orden']))

    saldo = Decimal('0.00')
    filas = []
    for m in movimientos:
        saldo += m['debe'] - m['haber']
        filas.append({
            'fecha': m['fecha'].isoformat(), 'tipo': m['tipo'], 'concepto': m['concepto'], 'periodo': m['periodo'],
            'debe': str(m['debe']), 'haber': str(m['haber']), 'saldo': str(redondear(saldo)),
            'vencimiento': m['vencimiento'].isoformat() if m['vencimiento'] else None, 'referencia': m['referencia'],
        })

    vencido = sum((c.saldo_usd for c in Cargo.objects.filter(unidad=unidad, estado='pendiente', fecha_vencimiento__lt=hasta)), Decimal('0.00'))
    return {
        'unidad_id': unidad.pk, 'unidad': str(unidad), 'hasta': hasta.isoformat(),
        'saldo_usd': str(redondear(saldo)), 'vencido_usd': str(redondear(vencido)),
        'saldo_a_favor_usd': str(saldo_a_favor_unidad(unidad)), 'movimientos': filas,
    }


def estado_solvencia(unidad: Unidad, *, hoy: date | None = None) -> dict:
    """Una unidad es solvente si no tiene ninguna deuda vencida (puede tener cuotas por vencer)."""
    hoy = hoy or timezone.localdate()
    vencidos = [c for c in Cargo.objects.filter(unidad=unidad, estado='pendiente', fecha_vencimiento__lt=hoy) if c.saldo_usd > 0]
    return {
        'solvente': not vencidos, 'fecha': hoy,
        'vencido_usd': redondear(sum((c.saldo_usd for c in vencidos), Decimal('0.00'))),
        'cuotas_vencidas': [c.concepto for c in vencidos],
    }


def metricas_tablero(hoy: date | None = None) -> dict:
    hoy = hoy or timezone.localdate()
    pendientes = [c for c in Cargo.objects.filter(estado='pendiente') if c.saldo_usd > 0]
    vencida = sum((c.saldo_usd for c in pendientes if c.fecha_vencimiento < hoy), Decimal('0.00'))
    por_vencer = sum((c.saldo_usd for c in pendientes if c.fecha_vencimiento >= hoy), Decimal('0.00'))

    inicio_mes = primer_dia(periodo_de(hoy))
    cobrado_mes = Recibo.objects.filter(estado='confirmado', fecha__gte=inicio_mes, fecha__lte=hoy).aggregate(t=Sum('monto_usd'))['t']
    facturado_mes = Cargo.objects.filter(fecha_emision__gte=inicio_mes, fecha_emision__lte=hoy).exclude(estado='anulado').aggregate(t=Sum('monto_usd'))['t']

    morosidad = reporte_morosidad(fecha_corte=hoy)
    por_estado = {fila['estado']: fila['n'] for fila in Unidad.objects.filter(activo=True).values('estado').annotate(n=Count('id'))}

    vencen = {}
    for dias in (30, 60, 90):
        vencen[str(dias)] = Contrato.objects.filter(estado='vigente', fecha_fin__gte=hoy, fecha_fin__lte=hoy + timedelta(days=dias)).count()

    return {
        'cartera_vencida_usd': str(redondear(vencida)),
        'cartera_por_vencer_usd': str(redondear(por_vencer)),
        'cobrado_mes_usd': str(redondear(cobrado_mes)),
        'facturado_mes_usd': str(redondear(facturado_mes)),
        'morosidad': morosidad['resumen'],
        'top_morosos': morosidad['filas'][:5],
        'unidades_por_estado': por_estado,
        'unidades_total': Unidad.objects.filter(activo=True).count(),
        'contratos_vigentes': Contrato.objects.filter(estado='vigente').count(),
        'contratos_por_vencer': vencen,
        'contratos_vencidos_con_inquilino': Contrato.objects.filter(estado='vencido', unidad__estado='ocupada', unidad__ocupante=F('inquilino')).count(),
        'pagos_por_revisar': PagoReportado.objects.filter(estado='pendiente').count(),
        'consultas_nuevas': ConsultaPropiedad.objects.filter(estado='nueva').count(),
    }


def recordatorios_morosidad(*, fecha_corte: date | None = None, edificio_id: int | None = None) -> list[dict]:
    """Un mensaje de WhatsApp listo para cada moroso con teléfono (el panel arma el enlace wa.me)."""
    reporte = reporte_morosidad(fecha_corte=fecha_corte, edificio_id=edificio_id)
    mensajes = []
    for fila in reporte['filas']:
        if not fila['telefono']:
            continue
        mensajes.append({
            'unidad_id': fila['unidad_id'], 'responsable_id': fila['responsable_id'], 'telefono': fila['telefono'],
            'responsable': fila['responsable'], 'unidad': fila['unidad'], 'total_vencido_usd': fila['total_vencido_usd'],
            'meses_vencidos': fila['meses_vencidos'],
        })
    return mensajes
