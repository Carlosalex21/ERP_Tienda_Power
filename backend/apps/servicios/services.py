"""Servicios de negocio del módulo de Órdenes de Servicio (taller)."""
from __future__ import annotations

from django.utils import timezone

from apps.facturacion.models import Factura, Detallefactura
from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura
from apps.facturacion.services.pagos_service import procesar_pago_factura_service
from apps.configuracion.models import Moneda
from apps.inventario.models import Almacen, Producto

from .models import OrdenServicio


class CerrarOrdenServicioError(Exception):
    """Error controlado al cerrar/cobrar una orden de servicio."""


def cerrar_orden_servicio(
    orden: OrdenServicio,
    lineas: list[dict],
    metodo_pago_id: int,
    usuario,
    condicion_pago: str = 'contado',
    moneda_id: int | None = None,
) -> Factura:
    """
    Convierte una orden ya lista/entregada en una `Factura` real y la cobra
    de una vez. `lineas` es una lista de `{producto_id, cantidad, monto}` --
    normalmente la mano de obra (ej. "Servicio Técnico") MÁS cualquier
    repuesto/pieza real que se haya vendido en esta orden (ej. "Batería
    nueva"), ya que un taller casi nunca cobra solo mano de obra. Cada línea
    reutiliza el mismo `Detallefactura` que usa cualquier venta; `monto` es
    lo que de verdad se cobró en ESA línea (puede diferir del precio de
    catálogo del producto).
    """
    if orden.estado == 'cancelado':
        raise CerrarOrdenServicioError("Esta orden está cancelada.")
    if orden.factura_id:
        raise CerrarOrdenServicioError("Esta orden ya fue facturada.")
    if not lineas:
        raise CerrarOrdenServicioError("Agrega al menos una línea (mano de obra o repuesto) para facturar.")

    productos_por_id = {
        p.id: p for p in Producto.objects.filter(pk__in=[l['producto_id'] for l in lineas], activo=True)
    }
    faltantes = [l['producto_id'] for l in lineas if l['producto_id'] not in productos_por_id]
    if faltantes:
        raise CerrarOrdenServicioError("Uno o más productos/servicios seleccionados no existen.")

    # El admin elige en qué moneda está cobrando ESTA orden (ej. un tenant
    # con base COP puede querer cobrar en USD un servicio puntual) -- si no
    # especifica ninguna, se usa la moneda base del tenant (comportamiento
    # anterior).
    moneda = Moneda.objects.filter(pk=moneda_id).first() if moneda_id else None
    if moneda is None:
        moneda = Moneda.objects.filter(es_predeterminada=True).first()
    almacen = Almacen.objects.first()

    factura = Factura.objects.create(
        usuario=usuario,
        vendedor=orden.tecnico or usuario,
        condicion_pago=condicion_pago,
        cliente=orden.cliente,
        fecha_operacion=timezone.now(),
        moneda=moneda,
        almacen=almacen,
        estado='abierta',
    )
    for linea in lineas:
        Detallefactura.objects.create(
            factura=factura,
            producto=productos_por_id[linea['producto_id']],
            cantidad=linea['cantidad'],
            precio_unitario=linea['monto'],
        )
    recalcular_y_guardar_factura(factura)

    pagos = [{
        "metodo_pago_id": metodo_pago_id,
        "monto": factura.total,
        "monto_recibido": factura.total,
    }]
    try:
        factura, _transacciones = procesar_pago_factura_service(
            factura_id=factura.id,
            pagos=pagos,
            estado_override='',
            datos_adicionales={},
            usuario=usuario,
        )
    except ValueError as exc:
        raise CerrarOrdenServicioError(str(exc)) from exc

    orden.estado = 'entregado'
    orden.factura = factura
    orden.fecha_entrega_real = timezone.now()
    orden.save(update_fields=['estado', 'factura', 'fecha_entrega_real'])
    return factura
