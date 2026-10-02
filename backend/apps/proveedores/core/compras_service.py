# apps/proveedores/core/compras_service.py
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.proveedores.models import OrdenCompra, OrdenCompraDetalle


class OrdenCompraError(Exception):
    """Error controlado al crear/enviar/recibir/cancelar una orden de compra."""


@transaction.atomic
def crear_orden_compra(*, proveedor_id, detalles_data, usuario, almacen_id=None, observaciones=''):
    """
    Crea una orden de compra en 'borrador' -- todavía NO toca stock ni
    genera ninguna cuenta por pagar (eso solo pasa al recibirla, ver
    `registrar_recepcion_orden_compra`). `detalles_data` es una lista de
    `{producto_id, cantidad, costo_unitario_esperado}`.
    """
    if not detalles_data:
        raise OrdenCompraError('La orden debe tener al menos un producto.')

    orden = OrdenCompra.objects.create(
        proveedor_id=proveedor_id, almacen_id=almacen_id, usuario=usuario, observaciones=observaciones,
    )
    for detalle in detalles_data:
        cantidad = detalle['cantidad']
        if cantidad <= 0:
            raise OrdenCompraError('La cantidad de cada línea debe ser mayor a cero.')
        OrdenCompraDetalle.objects.create(
            orden=orden,
            producto_id=detalle['producto_id'],
            cantidad_pedida=cantidad,
            costo_unitario_esperado=detalle.get('costo_unitario_esperado'),
        )
    return orden


def enviar_orden_compra(orden: OrdenCompra) -> OrdenCompra:
    """Marca la orden como enviada al proveedor -- solo un cambio de estado, informativo."""
    if orden.estado != 'borrador':
        raise OrdenCompraError('Solo una orden en borrador se puede marcar como enviada.')
    orden.estado = 'enviada'
    orden.fecha_envio = timezone.now()
    orden.save(update_fields=['estado', 'fecha_envio'])
    return orden


@transaction.atomic
def cancelar_orden_compra(orden: OrdenCompra) -> OrdenCompra:
    if orden.estado in ('cancelada', 'recibida'):
        raise OrdenCompraError('Esta orden ya está cancelada o completamente recibida.')
    if orden.detalles.filter(cantidad_recibida__gt=0).exists():
        raise OrdenCompraError('Esta orden ya tiene mercancía recibida -- no se puede cancelar, solo completar o dejar parcial.')
    orden.estado = 'cancelada'
    orden.save(update_fields=['estado'])
    return orden


def recibir_lineas_orden_compra(orden: OrdenCompra, lineas: list[tuple[int, int]]) -> dict[int, OrdenCompraDetalle]:
    """
    Suma a la orden lo que llegó con una factura de compra (ver
    `facturas_compra_service.registrar_factura_compra`, que es quien mueve
    el stock y crea la deuda). `lineas` es una lista de
    `(orden_detalle_id, cantidad)`. Valida que nada exceda lo pendiente y
    actualiza el estado de la orden. Devuelve los detalles por id.
    """
    if orden.estado not in ('enviada', 'recibida_parcial'):
        raise OrdenCompraError('Solo una orden enviada o parcialmente recibida se puede recibir.')

    detalles_por_id = {d.id: d for d in orden.detalles.select_for_update().select_related('producto')}
    for detalle_id, cantidad in lineas:
        detalle = detalles_por_id.get(detalle_id)
        if detalle is None:
            raise OrdenCompraError('Una de las líneas indicadas no pertenece a esta orden de compra.')
        if cantidad > detalle.cantidad_pendiente:
            raise OrdenCompraError(
                f'No puedes recibir {cantidad} de "{detalle.producto.nombre}" -- solo quedan {detalle.cantidad_pendiente} pendientes en la OC-{orden.numero}.'
            )
        detalle.cantidad_recibida += cantidad
        detalle.save(update_fields=['cantidad_recibida'])

    _actualizar_estado_recepcion(orden)
    return detalles_por_id


def revertir_lineas_orden_compra(orden: OrdenCompra, lineas: list[tuple[int, int]]) -> None:
    """Deshace `recibir_lineas_orden_compra` (al anular la factura con la que llegó la mercancía)."""
    detalles_por_id = {d.id: d for d in orden.detalles.select_for_update()}
    for detalle_id, cantidad in lineas:
        detalle = detalles_por_id.get(detalle_id)
        if detalle is None:
            continue
        detalle.cantidad_recibida = max(detalle.cantidad_recibida - cantidad, 0)
        detalle.save(update_fields=['cantidad_recibida'])
    _actualizar_estado_recepcion(orden)


def _actualizar_estado_recepcion(orden: OrdenCompra) -> None:
    # `.filter(...)` (a diferencia de `.all()`) siempre golpea la BD de
    # nuevo, sin importar que `orden` haya llegado con `detalles` ya
    # precargado (`prefetch_related`) desde el viewset.
    if orden.estado == 'cancelada':
        return
    if not orden.detalles.filter(cantidad_recibida__lt=F('cantidad_pedida')).exists():
        orden.estado = 'recibida'
        orden.fecha_recepcion_completa = orden.fecha_recepcion_completa or timezone.now()
    elif orden.detalles.filter(cantidad_recibida__gt=0).exists():
        orden.estado = 'recibida_parcial'
        orden.fecha_recepcion_completa = None
    else:
        orden.estado = 'enviada'
        orden.fecha_recepcion_completa = None
    orden.save(update_fields=['estado', 'fecha_recepcion_completa'])
