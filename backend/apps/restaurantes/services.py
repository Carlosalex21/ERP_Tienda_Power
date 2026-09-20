"""
Servicios de negocio del módulo de Restaurante.

Reutiliza el motor de facturación/pagos ya existente (cálculo de IVA,
correlativo, descuento de stock) en vez de reimplementarlo -- un pedido de
mesa solo se convierte en una `Factura` real al cerrarse (ver
`cerrar_pedido_mesa`); mientras está abierto, es solo una lista de ítems
sin ningún efecto fiscal.
"""
from __future__ import annotations

from django.utils import timezone

from apps.facturacion.models import Factura, Detallefactura
from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura
from apps.facturacion.services.pagos_service import procesar_pago_factura_service
from apps.configuracion.models import Moneda
from apps.configuracion.services.conversion_service import (
    convertir, MonedaNoEncontradaError, TasaNoDisponibleError,
)
from apps.inventario.models import Almacen

from .models import PedidoMesa


class CerrarPedidoMesaError(Exception):
    """Error controlado al cerrar/cobrar un pedido de mesa."""


def cerrar_pedido_mesa(
    pedido: PedidoMesa,
    metodo_pago_id: int,
    usuario,
    condicion_pago: str = 'contado',
    moneda_id: int | None = None,
) -> Factura:
    """
    Convierte un `PedidoMesa` abierto en una `Factura` real, la cobra de una
    vez (pago de contado completo -- pago dividido/abono queda para una
    iteración futura) y descuenta el stock vendido.
    """
    if pedido.estado != 'abierto':
        raise CerrarPedidoMesaError("Este pedido ya está cerrado.")

    items = list(pedido.items.select_related('producto__moneda').all())
    if not items:
        raise CerrarPedidoMesaError("La mesa no tiene ítems que facturar.")

    moneda_base = Moneda.objects.filter(es_predeterminada=True).first()
    # El mesero elige en qué moneda cobra la mesa (ej. un tenant con base COP
    # puede querer cobrar en USD) -- si no especifica ninguna, se usa la
    # moneda base (comportamiento anterior).
    moneda_cobro = Moneda.objects.filter(pk=moneda_id).first() if moneda_id else None
    if moneda_cobro is None:
        moneda_cobro = moneda_base
    almacen = Almacen.objects.first()

    factura = Factura.objects.create(
        usuario=usuario,
        vendedor=pedido.mesero or usuario,
        condicion_pago=condicion_pago,
        cliente=pedido.cliente,
        fecha_operacion=timezone.now(),
        moneda=moneda_cobro,
        almacen=almacen,
        estado='abierta',
    )
    for item in items:
        precio = item.precio_unitario
        # Cada ítem quedó guardado en la moneda que tenía el producto al
        # agregarlo (o la base, si el producto no tiene moneda propia) -- si
        # se está cobrando en una moneda distinta, hay que convertir para no
        # tratar, por ejemplo, un precio en COP como si fuera USD.
        moneda_item_codigo = item.producto.moneda.codigo if item.producto.moneda else moneda_base.codigo
        if moneda_item_codigo != moneda_cobro.codigo:
            try:
                precio = convertir(precio, moneda_item_codigo, moneda_cobro.codigo)
            except (MonedaNoEncontradaError, TasaNoDisponibleError):
                pass  # sin tasa vigente, se deja el número tal cual antes que bloquear el cobro
        Detallefactura.objects.create(
            factura=factura,
            producto=item.producto,
            cantidad=item.cantidad,
            precio_unitario=precio,
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
        raise CerrarPedidoMesaError(str(exc)) from exc

    pedido.estado = 'cerrado'
    pedido.factura = factura
    pedido.fecha_cierre = timezone.now()
    pedido.save(update_fields=['estado', 'factura', 'fecha_cierre'])
    return factura
