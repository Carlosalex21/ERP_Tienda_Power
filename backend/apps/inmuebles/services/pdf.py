"""Generación de los PDF del módulo (recibo, estado de cuenta, solvencia, recibo de condominio, liquidación)."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from apps.core.pdf_utils import obtener_logo_base64
from apps.inmuebles.models import Cargo, GastoComun, Liquidacion, MedioPago, Recibo, Unidad
from apps.inmuebles.services import cobranza, reportes


def _contexto_base() -> dict:
    from apps.configuracion.models import ConfiguracionEmpresa

    empresa, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
    return {'empresa': empresa, 'logo_base64': obtener_logo_base64(empresa.logo), 'generado': timezone.now()}


def _renderizar(plantilla: str, contexto: dict) -> bytes:
    html = render_to_string(f'inmuebles/{plantilla}', {**_contexto_base(), **contexto})
    salida = BytesIO()
    resultado = pisa.CreatePDF(html, dest=salida)
    if resultado.err:
        raise RuntimeError('No se pudo generar el PDF.')
    return salida.getvalue()


def pdf_recibo(recibo: Recibo) -> bytes:
    return _renderizar('recibo.html', {
        'recibo': recibo, 'unidad': recibo.unidad, 'pagador': recibo.pagador.nombre if recibo.pagador else '',
        'aplicaciones': list(recibo.aplicaciones.select_related('cargo')),
        'saldo_pendiente': cobranza.saldo_pendiente_unidad(recibo.unidad),
    })


def pdf_estado_cuenta(unidad: Unidad) -> bytes:
    responsable = unidad.responsable_pago
    return _renderizar('estado_cuenta.html', {
        'unidad': unidad, 'responsable': responsable.nombre if responsable else '', 'reporte': reportes.estado_cuenta(unidad),
    })


def pdf_solvencia(unidad: Unidad) -> bytes:
    responsable = unidad.responsable_pago
    return _renderizar('solvencia.html', {
        'unidad': unidad, 'responsable': responsable.nombre if responsable else '', 'estado': reportes.estado_solvencia(unidad),
    })


def pdf_recibo_condominio(cargo: Cargo) -> bytes:
    periodo = cargo.periodo_condominio
    if periodo is None:
        raise cobranza.CobranzaError('Este cargo no corresponde a una cuota de condominio.')
    gastos = [
        {'nombre': dict(GastoComun.CATEGORIA_CHOICES).get(fila['categoria'], fila['categoria']), 'total': fila['total']}
        for fila in GastoComun.objects.filter(edificio=periodo.edificio, periodo=periodo.periodo)
        .values('categoria').annotate(total=Sum('monto_usd')).order_by('categoria')
    ]
    medios = MedioPago.objects.filter(Q(edificio=periodo.edificio) | Q(edificio__isnull=True), activo=True)
    try:
        base = cobranza.moneda_base_codigo()
        tasa = {'moneda': base, 'valor': cobranza.tasa_usd_para_fecha(timezone.localdate())} if base != 'USD' else None
    except cobranza.CobranzaError:
        tasa = None
    saldo = cargo.saldo_usd
    responsable = cargo.unidad.responsable_pago
    return _renderizar('recibo_condominio.html', {
        'cargo': cargo, 'periodo': periodo, 'gastos': gastos, 'medios': list(medios), 'saldo': saldo,
        'responsable': responsable.nombre if responsable else '', 'tasa': tasa,
        'equivalente': (saldo * tasa['valor']) if tasa else Decimal('0'),
    })


def pdf_liquidacion(liquidacion: Liquidacion) -> bytes:
    return _renderizar('liquidacion.html', {'liquidacion': liquidacion, 'lineas': list(liquidacion.lineas.all())})
