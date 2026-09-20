"""
Servicio de pedidos B2B.

Crea una ``Factura`` para un cliente B2B autenticado, aplicando el precio
efectivo de su ``NivelPrecio`` a cada línea (no el precio de lista) -- ver
``pricing_service.calcular_precio_efectivo``. Antes de este servicio no
existía ningún endpoint para que un cliente B2B autenticado efectivamente
comprara: solo podía ver su catálogo con precio.

También aplica, sobre el pedido recién creado:
- Selección de variante/SKU para productos ``tipo='variable'`` (antes solo
  se podía vender el producto padre, ignorando stock/precio por variante).
- Verificación de línea de crédito (``credit_service``).
- Recalculo automático del nivel de precio por volumen histórico
  (``pricing_tier_service``), para que el SIGUIENTE pedido ya cobre al
  nivel que el cliente acaba de alcanzar.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.configuracion.services.conversion_service import get_moneda_base, convertir
from apps.facturacion.models import Factura, Detallefactura
from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura
from apps.inventario.models import Producto, Variacionproducto
from apps.inventario.services.stock_service import reducir_stock_item

from . import credit_service, pricing_tier_service
from .pricing_service import calcular_precio_efectivo


class B2BOrderCreationError(Exception):
    """Error controlado al crear un pedido B2B (producto inválido, sin stock, etc.)."""


@transaction.atomic
def crear_pedido_b2b(cliente_b2b, items: list[dict]) -> Factura:
    """
    Crea un pedido (``Factura`` en estado 'pendiente') para un cliente B2B.

    Args:
        cliente_b2b: Instancia de ``ClienteB2B`` autenticado.
        items: Lista de ``{'producto_id': int, 'cantidad': int, 'variante_id': int | None}``.

    Returns:
        Factura: la factura creada, con totales ya calculados.

    Raises:
        B2BOrderCreationError: si el carrito está vacío, un producto/variante
            no existe/no está disponible, no hay stock suficiente, o el
            pedido excede la línea de crédito disponible del cliente.
    """
    if not items:
        raise B2BOrderCreationError("El carrito está vacío.")

    disponible_antes = credit_service.credito_disponible(cliente_b2b)

    # Moneda base del tenant: igual que en `order_service.crear_orden_desde_pedido_publico`,
    # el pedido se registra siempre en ella (ver conversión de `precio_unitario`
    # más abajo), sin importar en qué moneda esté cargado el precio de cada producto.
    moneda_base = get_moneda_base()

    # `registrar_libro=False`: los totales todavía son 0 aquí (se calculan
    # más abajo con `recalcular_y_guardar_factura`), así que registrar esta
    # cabecera en el Libro de Ventas ahora mismo solo produciría una línea
    # en cero que ese segundo guardado reescribe de inmediato -- ver el
    # mismo comentario en `order_service.crear_orden_desde_pedido_publico`.
    # No se le asigna `correlativo` aquí: `pendiente_de_aprobacion=True`
    # hace que `Factura.save()` no le genere correlativo ni número de
    # control hasta que el admin confirme el pedido (puede rechazarlo) --
    # mismo criterio que `crear_orden_desde_pedido_publico`.
    factura = Factura(
        estado='pendiente',
        pendiente_de_aprobacion=True,
        moneda=moneda_base,
        fecha_operacion=timezone.now(),
        cliente_b2b=cliente_b2b,
        nombre_cliente_pendiente=cliente_b2b.razon_social,
        comentario_pendiente=f"Pedido B2B -- {cliente_b2b.email_contacto} (RIF {cliente_b2b.rif})",
    )
    factura.save(registrar_libro=False)

    for item in items:
        try:
            producto = Producto.objects.select_related('moneda').get(id=item['producto_id'], activo=True, disponible_online=True)
        except Producto.DoesNotExist:
            raise B2BOrderCreationError(f"El producto con ID {item['producto_id']} no existe o no está disponible.")

        variante = None
        variante_id = item.get('variante_id')
        if producto.tipo == 'variable':
            if not variante_id:
                raise B2BOrderCreationError(f"'{producto.nombre}' tiene variantes: elige una antes de pedirlo.")
            try:
                variante = Variacionproducto.objects.get(id=variante_id, producto=producto)
            except Variacionproducto.DoesNotExist:
                raise B2BOrderCreationError(f"La variante con ID {variante_id} no existe para '{producto.nombre}'.")
        elif variante_id:
            raise B2BOrderCreationError(f"'{producto.nombre}' no tiene variantes.")

        item_a_vender = variante or producto
        cantidad = int(item['cantidad'])
        precio_efectivo = calcular_precio_efectivo(item_a_vender, cliente_b2b)
        # `precio_efectivo` puede venir en la moneda propia del producto
        # (`producto.moneda`) -- convertir a la moneda base de la factura,
        # ver mismo criterio y comentario en `order_service.crear_orden_desde_pedido_publico`.
        if producto.moneda_id and producto.moneda.codigo != moneda_base.codigo:
            precio_efectivo = convertir(precio_efectivo, producto.moneda.codigo, moneda_base.codigo)

        try:
            reducir_stock_item(item_a_vender, cantidad)
        except ValueError as e:
            raise B2BOrderCreationError(str(e))

        Detallefactura.objects.create(
            factura=factura,
            producto=producto,
            variante=variante,
            cantidad=cantidad,
            precio_unitario=precio_efectivo,
        )

    recalcular_y_guardar_factura(factura)

    if disponible_antes is not None and factura.total > disponible_antes:
        raise B2BOrderCreationError(
            f"Este pedido (${factura.total}) excede tu crédito disponible (${disponible_antes})."
        )

    pricing_tier_service.recalcular_nivel_precio(cliente_b2b)

    return factura
