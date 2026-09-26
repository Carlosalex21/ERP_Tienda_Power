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


@transaction.atomic
def registrar_recepcion_orden_compra(*, orden: OrdenCompra, lineas_recibidas, numero_documento, usuario, motivo='compra_con_factura'):
    """
    Recibe (total o parcialmente) una orden de compra: por cada línea con
    cantidad > 0 recibida, aplica una ENTRADA real de inventario a través
    del mismo camino de siempre (`stock_service.crear_y_aplicar_ajuste`) --
    así, sin duplicar ni una línea de lógica, la recepción ya actualiza el
    costo promedio, genera su `CuentaPorPagar` con el proveedor y postea su
    asiento contable automático (ver Fase 6 y 9). Una orden de compra no es
    más que el paso "esto pedí" antes de esa misma entrada de siempre.

    `lineas_recibidas` es una lista de `{detalle_id, cantidad, costo_unitario}`.
    """
    from apps.inventario.services.stock_service import crear_y_aplicar_ajuste

    if orden.estado not in ('enviada', 'recibida_parcial'):
        raise OrdenCompraError('Solo una orden enviada o parcialmente recibida se puede recibir.')
    if not lineas_recibidas:
        raise OrdenCompraError('Indica al menos una línea con cantidad recibida.')

    detalles_por_id = {d.id: d for d in orden.detalles.select_for_update()}
    detalles_para_ajuste = []
    detalles_a_actualizar = []

    for linea in lineas_recibidas:
        detalle = detalles_por_id.get(linea['detalle_id'])
        if detalle is None:
            raise OrdenCompraError('Una de las líneas indicadas no pertenece a esta orden.')
        cantidad = linea['cantidad']
        if cantidad <= 0:
            continue
        if cantidad > detalle.cantidad_pendiente:
            raise OrdenCompraError(
                f'No puedes recibir {cantidad} de "{detalle.producto.nombre}" -- solo quedan {detalle.cantidad_pendiente} pendientes.'
            )
        costo = linea.get('costo_unitario') or detalle.costo_unitario_esperado
        detalles_para_ajuste.append({
            'producto_id': detalle.producto_id,
            'cantidad': cantidad,
            'costo_unitario': costo,
        })
        detalle.cantidad_recibida += cantidad
        detalles_a_actualizar.append(detalle)

    if not detalles_para_ajuste:
        raise OrdenCompraError('Ninguna línea tiene cantidad recibida mayor a cero.')

    ajuste = crear_y_aplicar_ajuste(
        usuario=usuario,
        detalles_data=detalles_para_ajuste,
        tipo='entrada',
        motivo=motivo,
        proveedor_id=orden.proveedor_id,
        almacen_id=orden.almacen_id,
        numero_documento=numero_documento or f'OC-{orden.numero}',
        observaciones=f'Recepción de la Orden de Compra OC-{orden.numero}',
    )

    for detalle in detalles_a_actualizar:
        detalle.save(update_fields=['cantidad_recibida'])

    # `.filter(...)` (a diferencia de `.all()`) siempre golpea la BD de
    # nuevo, sin importar que `orden` haya llegado con `detalles` ya
    # precargado (`prefetch_related`) desde el viewset -- necesario para ver
    # reflejadas las líneas que se acaban de guardar arriba, y también las
    # que ya se habían completado en una recepción anterior.
    quedan_pendientes = orden.detalles.filter(cantidad_recibida__lt=F('cantidad_pedida')).exists()
    if not quedan_pendientes:
        orden.estado = 'recibida'
        orden.fecha_recepcion_completa = timezone.now()
        orden.save(update_fields=['estado', 'fecha_recepcion_completa'])
    else:
        orden.estado = 'recibida_parcial'
        orden.save(update_fields=['estado'])

    return orden, ajuste
