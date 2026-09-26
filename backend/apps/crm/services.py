"""Servicios de negocio del CRM ligero: oportunidades y cotizaciones."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Cotizacion, CotizacionDetalle, Oportunidad

CENT = Decimal('0.01')


class CrmError(Exception):
    """Error controlado al crear/actualizar una oportunidad o cotización."""


def _round(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


# --- Oportunidades ---

def crear_oportunidad(*, titulo, usuario, cliente_id=None, nombre_prospecto='', telefono_prospecto='',
                       valor_estimado=None, fecha_cierre_estimada=None, proximo_seguimiento=None,
                       usuario_asignado_id=None, departamento_id=None, observaciones=''):
    if not titulo.strip():
        raise CrmError('La oportunidad necesita un título.')
    if not cliente_id and not nombre_prospecto.strip():
        raise CrmError('Indica un cliente registrado o al menos el nombre del prospecto.')
    return Oportunidad.objects.create(
        titulo=titulo.strip(), cliente_id=cliente_id, nombre_prospecto=nombre_prospecto.strip(),
        telefono_prospecto=telefono_prospecto.strip(), valor_estimado=valor_estimado,
        fecha_cierre_estimada=fecha_cierre_estimada, proximo_seguimiento=proximo_seguimiento,
        usuario_asignado_id=usuario_asignado_id or (usuario.id if usuario else None),
        departamento_id=departamento_id, observaciones=observaciones.strip(),
    )


def actualizar_etapa_oportunidad(oportunidad: Oportunidad, etapa: str, motivo_perdida: str = '') -> Oportunidad:
    if etapa not in dict(Oportunidad.ETAPA_CHOICES):
        raise CrmError('Etapa inválida.')
    oportunidad.etapa = etapa
    if etapa == 'perdido':
        oportunidad.motivo_perdida = motivo_perdida.strip()
    oportunidad.save(update_fields=['etapa', 'motivo_perdida'])
    return oportunidad


# --- Cotizaciones ---

def _recalcular_totales_cotizacion(cotizacion: Cotizacion) -> None:
    subtotal = sum((d.subtotal_linea for d in cotizacion.detalles.all()), Decimal('0.00'))
    cotizacion.subtotal = _round(subtotal)
    # El IVA real se calcula recién al convertirla en una venta de verdad
    # (`recalcular_y_guardar_factura` ya sabe aplicar la estrategia fiscal
    # del tenant) -- una cotización no es un documento fiscal, así que aquí
    # el "total" es solo el subtotal acordado con el cliente.
    cotizacion.total = cotizacion.subtotal
    cotizacion.save(update_fields=['subtotal', 'total'])


@transaction.atomic
def crear_cotizacion(*, usuario, detalles_data, cliente_id=None, nombre_prospecto='', telefono_prospecto='',
                      oportunidad_id=None, moneda_id=None, fecha_vencimiento=None, observaciones=''):
    if not cliente_id and not nombre_prospecto.strip():
        raise CrmError('Indica un cliente registrado o al menos el nombre del prospecto.')
    if not detalles_data:
        raise CrmError('La cotización debe tener al menos un producto.')

    cotizacion = Cotizacion.objects.create(
        cliente_id=cliente_id, nombre_prospecto=nombre_prospecto.strip(), telefono_prospecto=telefono_prospecto.strip(),
        oportunidad_id=oportunidad_id, moneda_id=moneda_id, fecha_vencimiento=fecha_vencimiento,
        observaciones=observaciones.strip(), usuario=usuario,
    )
    for detalle in detalles_data:
        cantidad = detalle['cantidad']
        if cantidad <= 0:
            raise CrmError('La cantidad de cada línea debe ser mayor a cero.')
        CotizacionDetalle.objects.create(
            cotizacion=cotizacion, producto_id=detalle['producto_id'], variante_id=detalle.get('variante_id'),
            cantidad=cantidad, precio_unitario=detalle['precio_unitario'],
        )
    _recalcular_totales_cotizacion(cotizacion)

    # Si nació de una oportunidad, la mueve sola a la etapa "cotizado" --
    # un seguimiento comercial real: cotizar es un paso del pipeline, no
    # algo aparte que alguien tenga que ir a marcar a mano dos veces.
    if cotizacion.oportunidad_id and cotizacion.oportunidad.etapa in ('nuevo', 'contactado'):
        actualizar_etapa_oportunidad(cotizacion.oportunidad, 'cotizado')

    return cotizacion


def cambiar_estado_cotizacion(cotizacion: Cotizacion, nuevo_estado: str) -> Cotizacion:
    transiciones_validas = {
        'borrador': {'enviada'},
        'enviada': {'aceptada', 'rechazada', 'vencida'},
    }
    if nuevo_estado not in transiciones_validas.get(cotizacion.estado, set()):
        raise CrmError(f'No se puede pasar una cotización de "{cotizacion.estado}" a "{nuevo_estado}".')
    cotizacion.estado = nuevo_estado
    cotizacion.save(update_fields=['estado'])
    return cotizacion


@transaction.atomic
def convertir_cotizacion_a_venta(cotizacion: Cotizacion, *, usuario, condicion_pago='contado', almacen_id=None):
    """
    Crea la venta real (una `Factura` en estado 'abierta', sin cobrar
    todavía) a partir de una cotización aceptada -- desde ahí sigue el
    camino normal de siempre (POS/Pedidos la cobra cuando corresponda, y
    recién ESE paso descuenta inventario real). La cotización nunca tocó
    stock ni caja por sí sola.
    """
    from apps.facturacion.models import Factura, Detallefactura
    from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura

    if cotizacion.estado != 'aceptada':
        raise CrmError('Solo una cotización aceptada se puede convertir en venta.')
    if cotizacion.factura_generada_id:
        raise CrmError('Esta cotización ya fue convertida en una venta.')
    if not cotizacion.cliente_id:
        raise CrmError('Esta cotización no tiene un cliente registrado -- regístralo antes de convertirla en venta.')

    factura = Factura.objects.create(
        usuario=usuario, vendedor=usuario, condicion_pago=condicion_pago, cliente=cotizacion.cliente,
        fecha_operacion=timezone.now(), moneda=cotizacion.moneda, almacen_id=almacen_id, estado='abierta',
    )
    for detalle in cotizacion.detalles.all():
        Detallefactura.objects.create(
            factura=factura, producto=detalle.producto, variante=detalle.variante,
            cantidad=detalle.cantidad, precio_unitario=detalle.precio_unitario,
        )
    recalcular_y_guardar_factura(factura)

    cotizacion.estado = 'convertida'
    cotizacion.factura_generada = factura
    cotizacion.save(update_fields=['estado', 'factura_generada'])

    if cotizacion.oportunidad_id:
        actualizar_etapa_oportunidad(cotizacion.oportunidad, 'ganado')

    return factura
