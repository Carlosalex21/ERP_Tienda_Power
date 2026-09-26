"""Servicios de negocio de Postventa: generación automática de garantías y gestión de reclamos."""
from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import Garantia, ReclamoPostventa


class PostventaError(Exception):
    """Error controlado al gestionar un reclamo postventa."""


def _sumar_meses(fecha: date, meses: int) -> date:
    """Suma `meses` a `fecha` sin depender de `python-dateutil` (no es una dependencia garantizada del proyecto)."""
    mes_total = fecha.month - 1 + meses
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(fecha.day, [31, 29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1])
    return date(anio, mes, dia)


def generar_garantias_de_factura(factura) -> list[Garantia]:
    """
    Crea una `Garantia` por cada línea de `factura` cuyo producto tenga
    `meses_garantia` asignado -- se llama justo después de que la factura
    queda 'pagado' (mismo punto donde ya se dispara el asiento contable
    automático de la venta), y es idempotente: si ya existe una garantía
    para esa línea (`OneToOneField`), simplemente se salta en vez de
    duplicarla o fallar.
    """
    fecha_inicio = (factura.fecha_pago or factura.fecha_operacion or timezone.now()).date()
    creadas = []
    for detalle in factura.detalles.select_related('producto').all():
        producto = detalle.producto
        if not producto or not producto.meses_garantia:
            continue
        if Garantia.objects.filter(detalle_factura=detalle).exists():
            continue
        garantia = Garantia.objects.create(
            detalle_factura=detalle,
            factura=factura,
            producto=producto,
            cliente=factura.cliente,
            fecha_inicio=fecha_inicio,
            fecha_vencimiento=_sumar_meses(fecha_inicio, producto.meses_garantia),
            meses_garantia=producto.meses_garantia,
        )
        creadas.append(garantia)
    return creadas


@transaction.atomic
def crear_reclamo(*, titulo, descripcion='', cliente_id=None, nombre_contacto_libre='', telefono_contacto='',
                   factura_id=None, producto_id=None, garantia_id=None, prioridad='media', usuario_creador=None) -> ReclamoPostventa:
    if not titulo or not titulo.strip():
        raise PostventaError('El reclamo necesita un título.')
    if cliente_id is None and not nombre_contacto_libre.strip():
        raise PostventaError('Indica un cliente registrado o al menos un nombre de contacto.')

    reclamo = ReclamoPostventa.objects.create(
        titulo=titulo.strip(), descripcion=descripcion.strip(), cliente_id=cliente_id,
        nombre_contacto_libre=nombre_contacto_libre.strip(), telefono_contacto=telefono_contacto.strip(),
        factura_id=factura_id, producto_id=producto_id, garantia_id=garantia_id, prioridad=prioridad,
        usuario_creador=usuario_creador,
    )

    # Aviso inmediato (Web Push) solo para prioridad alta -- uno media/baja
    # ya aparece en el Centro de Alertas la próxima vez que alguien lo
    # revise; uno alta amerita interrumpir aunque el panel esté cerrado.
    # Aislado con try/except: un fallo de Web Push jamás debe impedir que
    # el reclamo quede registrado.
    if prioridad == 'alta':
        try:
            from apps.restaurantes.push_notifications import enviar_push_a_staff
            enviar_push_a_staff(
                'Reclamo urgente', f'{reclamo.titulo} -- {reclamo.nombre_contacto}',
                url='/admin/postventa/reclamos',
            )
        except Exception:
            pass

    return reclamo


@transaction.atomic
def cambiar_estado_reclamo(reclamo: ReclamoPostventa, nuevo_estado: str, resolucion: str = '') -> ReclamoPostventa:
    if nuevo_estado not in dict(ReclamoPostventa.ESTADO_CHOICES):
        raise PostventaError('Estado inválido.')
    if reclamo.estado in ('resuelto', 'rechazado'):
        raise PostventaError('Este reclamo ya está cerrado.')

    reclamo.estado = nuevo_estado
    if resolucion.strip():
        reclamo.resolucion = resolucion.strip()
    if nuevo_estado in ('resuelto', 'rechazado'):
        reclamo.fecha_cierre = timezone.now()
    reclamo.save(update_fields=['estado', 'resolucion', 'fecha_cierre', 'fecha_actualizacion'])
    return reclamo
