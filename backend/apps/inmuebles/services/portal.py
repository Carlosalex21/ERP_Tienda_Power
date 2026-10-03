"""
Portal del condómino / inquilino / propietario.

Cada persona recibe un enlace secreto (por WhatsApp, junto a su recibo) donde ve
sus deudas, los datos para pagar y puede avisar un pago con su comprobante. La
administradora revisa el aviso y, al aprobarlo, se genera el recibo y se aplica
a las deudas.
"""
from __future__ import annotations

import logging
import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.inmuebles.models import Cargo, MedioPago, PagoReportado, PortalAcceso, Recibo, Unidad
from apps.inmuebles.services import cobranza
from apps.inmuebles.services.cobranza import CobranzaError, redondear
from apps.inmuebles.services.reportes import reporte_morosidad

logger = logging.getLogger(__name__)

METODOS_CON_REFERENCIA = ('transferencia', 'pago_movil', 'zelle', 'deposito')
DIAS_MAXIMOS_ATRAS = 120
MAX_PENDIENTES_POR_UNIDAD = 5


# --- Accesos ------------------------------------------------------------------

def obtener_o_crear_acceso(cliente) -> PortalAcceso:
    acceso = PortalAcceso.objects.filter(cliente=cliente, activo=True).first()
    if acceso is None:
        acceso = PortalAcceso.objects.create(cliente=cliente, token=secrets.token_urlsafe(24))
    return acceso


@transaction.atomic
def regenerar_acceso(cliente) -> PortalAcceso:
    """Invalida el enlace anterior (por si se filtró) y crea uno nuevo."""
    PortalAcceso.objects.filter(cliente=cliente, activo=True).update(activo=False)
    return PortalAcceso.objects.create(cliente=cliente, token=secrets.token_urlsafe(24))


def revocar_accesos(cliente) -> int:
    return PortalAcceso.objects.filter(cliente=cliente, activo=True).update(activo=False)


def acceso_por_token(token: str) -> PortalAcceso | None:
    acceso = PortalAcceso.objects.select_related('cliente').filter(token=token or '', activo=True, cliente__activo=True).first()
    if acceso:
        PortalAcceso.objects.filter(pk=acceso.pk).update(ultimo_acceso=timezone.now())
    return acceso


def unidades_de(cliente):
    """Unidades activas donde la persona es propietaria u ocupante."""
    return Unidad.objects.filter(activo=True).filter(Q(propietario=cliente) | Q(ocupante=cliente)).select_related('edificio').distinct()


# --- Datos del portal ---------------------------------------------------------

def _medios_de(unidad: Unidad) -> list[dict]:
    filtro = Q(edificio__isnull=True)
    if unidad.edificio_id:
        filtro |= Q(edificio_id=unidad.edificio_id)
    return [
        {
            'id': m.pk, 'tipo': m.tipo, 'tipo_display': m.get_tipo_display(), 'titular': m.titular, 'documento_titular': m.documento_titular,
            'banco': m.banco, 'numero_cuenta': m.numero_cuenta, 'moneda': m.moneda, 'instrucciones': m.instrucciones,
        }
        for m in MedioPago.objects.filter(filtro, activo=True).order_by('tipo', 'banco')
    ]


def _morosidad_edificio(unidad: Unidad, hoy: date) -> dict | None:
    edificio = unidad.edificio
    if edificio is None or not edificio.portal_muestra_morosidad:
        return None
    reporte = reporte_morosidad(fecha_corte=hoy, edificio_id=edificio.pk)
    return {
        'unidades_morosas': reporte['resumen']['unidades_morosas'],
        'total_unidades': reporte['resumen']['total_unidades'],
        'porcentaje_morosidad': reporte['resumen']['porcentaje_morosidad'],
        'unidades': [{'codigo': f['unidad'], 'meses_vencidos': f['meses_vencidos']} for f in reporte['filas']],
    }


def datos_portal(acceso: PortalAcceso) -> dict:
    from apps.configuracion.models import ConfiguracionEmpresa

    hoy = timezone.localdate()
    cliente = acceso.cliente
    empresa, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)

    try:
        base = cobranza.moneda_base_codigo()
        tasa = {'moneda': base, 'valor': str(cobranza.tasa_usd_para_fecha(hoy))} if base != 'USD' else None
    except CobranzaError:
        tasa = None

    unidades = []
    saldo_total = vencido_total = Decimal('0.00')
    for unidad in unidades_de(cliente):
        cargos = [c for c in Cargo.objects.filter(unidad=unidad, estado='pendiente').order_by('fecha_vencimiento', 'id') if c.saldo_usd > 0]
        saldo = sum((c.saldo_usd for c in cargos), Decimal('0.00'))
        vencido = sum((c.saldo_usd for c in cargos if c.fecha_vencimiento < hoy), Decimal('0.00'))
        saldo_total += saldo
        vencido_total += vencido
        unidades.append({
            'id': unidad.pk, 'codigo': unidad.codigo, 'edificio': unidad.edificio.nombre if unidad.edificio_id else '',
            'rol': 'propietario' if unidad.propietario_id == cliente.pk else 'inquilino',
            'saldo_usd': str(redondear(saldo)), 'vencido_usd': str(redondear(vencido)),
            'saldo_a_favor_usd': str(cobranza.saldo_a_favor_unidad(unidad)),
            'cargos': [
                {
                    'id': c.pk, 'concepto': c.concepto, 'periodo': c.periodo, 'tipo': c.tipo, 'monto_usd': str(c.monto_usd),
                    'saldo_usd': str(redondear(c.saldo_usd)), 'vencimiento': c.fecha_vencimiento.isoformat(), 'vencido': c.fecha_vencimiento < hoy,
                }
                for c in cargos
            ],
            'recibos': [
                {'id': r.pk, 'numero': r.numero, 'fecha': r.fecha.isoformat(), 'monto_usd': str(r.monto_usd), 'metodo': r.get_metodo_display()}
                for r in Recibo.objects.filter(unidad=unidad, estado='confirmado').order_by('-fecha', '-id')[:10]
            ],
            'medios_pago': _medios_de(unidad),
            'pagos_reportados': [
                {
                    'id': p.pk, 'fecha_pago': p.fecha_pago.isoformat(), 'monto_pago': str(p.monto_pago), 'moneda_pago': p.moneda_pago,
                    'estado': p.estado, 'estado_display': p.get_estado_display(), 'motivo_rechazo': p.motivo_rechazo, 'referencia': p.referencia,
                }
                for p in PagoReportado.objects.filter(unidad=unidad).order_by('-fecha_creacion')[:5]
            ],
            'morosidad_edificio': _morosidad_edificio(unidad, hoy),
        })

    return {
        'persona': {'nombre': cliente.nombre, 'documento': cliente.documento},
        'empresa': {'nombre': empresa.nombre_comercial, 'telefono': empresa.telefono},
        'tasa': tasa,
        'saldo_total_usd': str(redondear(saldo_total)),
        'vencido_total_usd': str(redondear(vencido_total)),
        'unidades': unidades,
    }


# --- Aviso de pago ------------------------------------------------------------

def _notificar_staff(pago: PagoReportado) -> None:
    try:
        from apps.restaurantes.push_notifications import enviar_push_a_staff
        enviar_push_a_staff(
            'Nuevo pago por revisar', f'{pago.unidad} reportó un pago de {pago.monto_pago} {pago.moneda_pago}.',
            url='/admin/inmuebles/pagos-reportados',
        )
    except Exception:
        logger.warning('No se pudo notificar el pago reportado %s', pago.pk, exc_info=True)


@transaction.atomic
def reportar_pago(
    acceso: PortalAcceso, *, unidad_id: int, fecha_pago: date, monto_pago, moneda_pago: str, metodo: str,
    referencia: str = '', banco: str = '', medio_pago_id: int | None = None, cargos_ids=None, comprobante=None, nota: str = '',
) -> PagoReportado:
    unidad = unidades_de(acceso.cliente).filter(pk=unidad_id).first()
    if unidad is None:
        raise CobranzaError('Esa unidad no está asociada a tu cuenta.')

    monto_pago = Decimal(monto_pago)
    if monto_pago <= 0:
        raise CobranzaError('El monto debe ser mayor a cero.')
    hoy = timezone.localdate()
    if fecha_pago > hoy:
        raise CobranzaError('La fecha del pago no puede ser futura.')
    if fecha_pago < hoy - timedelta(days=DIAS_MAXIMOS_ATRAS):
        raise CobranzaError(f'La fecha del pago no puede ser de hace más de {DIAS_MAXIMOS_ATRAS} días.')
    moneda_pago = (moneda_pago or '').upper()
    base = cobranza.moneda_base_codigo()
    if moneda_pago not in ('USD', base):
        raise CobranzaError(f'Solo se aceptan pagos en USD o en {base}.')
    referencia = (referencia or '').strip()
    if metodo in METODOS_CON_REFERENCIA and not referencia:
        raise CobranzaError('Indica el número de referencia de la operación.')

    if referencia and (
        PagoReportado.objects.filter(unidad=unidad, referencia=referencia, monto_pago=monto_pago).exclude(estado='rechazado').exists()
        or Recibo.objects.filter(unidad=unidad, referencia=referencia, monto_pago=monto_pago, estado='confirmado').exists()
    ):
        raise CobranzaError('Ya reportaste o registraste un pago con esa referencia y monto.')
    if PagoReportado.objects.filter(unidad=unidad, estado='pendiente').count() >= MAX_PENDIENTES_POR_UNIDAD:
        raise CobranzaError('Tienes varios pagos pendientes de revisión. Espera a que la administración los confirme.')

    medio = None
    if medio_pago_id:
        medio = MedioPago.objects.filter(pk=medio_pago_id, activo=True).first()
        if medio is None:
            raise CobranzaError('El medio de pago seleccionado no existe.')

    cargos = []
    if cargos_ids:
        cargos = list(Cargo.objects.filter(pk__in=cargos_ids, unidad=unidad, estado='pendiente'))
        if len(cargos) != len(set(cargos_ids)):
            raise CobranzaError('Alguna de las deudas seleccionadas ya no está pendiente.')

    pago = PagoReportado.objects.create(
        unidad=unidad, cliente=acceso.cliente, medio_pago=medio, metodo=metodo, fecha_pago=fecha_pago, referencia=referencia, banco=banco,
        moneda_pago=moneda_pago, monto_pago=monto_pago, comprobante=comprobante, nota=(nota or '')[:255],
    )
    if cargos:
        pago.cargos.set(cargos)
    _notificar_staff(pago)
    return pago


@transaction.atomic
def aprobar_pago_reportado(pago: PagoReportado, *, usuario, tasa=None, monto_pago=None, observaciones: str = '') -> PagoReportado:
    pago = PagoReportado.objects.select_for_update().get(pk=pago.pk)
    if pago.estado != 'pendiente':
        raise CobranzaError('Este pago ya fue revisado.')
    cargos = [c for c in pago.cargos.filter(estado='pendiente').order_by('fecha_vencimiento', 'id')]
    recibo = cobranza.registrar_recibo(
        usuario=usuario, unidad=pago.unidad, fecha=pago.fecha_pago, monto_pago=monto_pago if monto_pago is not None else pago.monto_pago,
        moneda_pago=pago.moneda_pago, tasa=tasa, metodo=pago.metodo, referencia=pago.referencia, banco=pago.banco,
        pagador=pago.cliente, cargos=cargos or None, comprobante=pago.comprobante or None,
        observaciones=observaciones or (f'Pago reportado desde el portal. {pago.nota}'.strip()),
    )
    pago.estado = 'aprobado'
    pago.recibo = recibo
    pago.revisado_por = usuario
    pago.fecha_revision = timezone.now()
    pago.save(update_fields=['estado', 'recibo', 'revisado_por', 'fecha_revision'])
    return pago


@transaction.atomic
def rechazar_pago_reportado(pago: PagoReportado, *, usuario, motivo: str) -> PagoReportado:
    pago = PagoReportado.objects.select_for_update().get(pk=pago.pk)
    if pago.estado != 'pendiente':
        raise CobranzaError('Este pago ya fue revisado.')
    if not (motivo or '').strip():
        raise CobranzaError('Indica el motivo del rechazo (el vecino lo verá).')
    pago.estado = 'rechazado'
    pago.motivo_rechazo = motivo.strip()[:255]
    pago.revisado_por = usuario
    pago.fecha_revision = timezone.now()
    pago.save(update_fields=['estado', 'motivo_rechazo', 'revisado_por', 'fecha_revision'])
    return pago
