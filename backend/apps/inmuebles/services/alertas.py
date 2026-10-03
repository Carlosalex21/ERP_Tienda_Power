"""Alertas del Centro de Alertas para condominios e inmobiliaria."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.inmuebles.models import ConsultaPropiedad, Contrato, PagoReportado
from apps.inmuebles.services.reportes import reporte_morosidad

DIAS_MORA_ATENCION = 30
DIAS_MORA_URGENTE = 60
DIAS_CONTRATO_URGENTE = 30
DIAS_CONTRATO_ATENCION = 60
HORAS_CONSULTA_SIN_ATENDER = 48


def alertas_inmuebles() -> list[dict]:
    hoy = timezone.localdate()
    alertas: list[dict] = []

    for fila in reporte_morosidad(fecha_corte=hoy)['filas']:
        dias = fila['dias_atraso']
        if dias <= DIAS_MORA_ATENCION:
            continue
        alertas.append({
            'tipo': 'morosidad', 'nivel': 'urgente' if dias > DIAS_MORA_URGENTE else 'atencion',
            'titulo': f"{fila['responsable']} -- {fila['unidad']}",
            'descripcion': f"${fila['total_vencido_usd']} vencido, {fila['meses_vencidos']} mes(es) de atraso",
            'link': '/admin/inmuebles/morosidad', 'dias': dias,
        })

    por_revisar = PagoReportado.objects.filter(estado='pendiente').count()
    if por_revisar:
        alertas.append({
            'tipo': 'pagos_reportados', 'nivel': 'atencion', 'titulo': f'{por_revisar} pago(s) por revisar',
            'descripcion': 'Condóminos o inquilinos avisaron un pago desde su portal.',
            'link': '/admin/inmuebles/pagos-reportados', 'dias': 0,
        })

    for contrato in Contrato.objects.filter(estado='vigente', fecha_fin__gte=hoy, fecha_fin__lte=hoy + timedelta(days=DIAS_CONTRATO_ATENCION)).select_related('unidad', 'inquilino'):
        faltan = (contrato.fecha_fin - hoy).days
        alertas.append({
            'tipo': 'contrato_por_vencer', 'nivel': 'urgente' if faltan <= DIAS_CONTRATO_URGENTE else 'atencion',
            'titulo': f'Contrato de {contrato.unidad} vence en {faltan} días',
            'descripcion': f'Inquilino: {contrato.inquilino.nombre}. Renueva o prepara la entrega.',
            'link': '/admin/inmuebles/contratos', 'dias': 60 - faltan,
        })

    limite = timezone.now() - timedelta(hours=HORAS_CONSULTA_SIN_ATENDER)
    sin_atender = ConsultaPropiedad.objects.filter(estado='nueva', fecha_creacion__lte=limite).count()
    if sin_atender:
        alertas.append({
            'tipo': 'consultas', 'nivel': 'atencion', 'titulo': f'{sin_atender} consulta(s) sin atender',
            'descripcion': 'Interesados en tus propiedades esperan respuesta hace más de 2 días.',
            'link': '/admin/inmuebles/consultas', 'dias': 2,
        })
    return alertas
