# apps/inventario/core/stock_service.py
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from apps.inventario.models import (
    Producto, Variacionproducto, MovimientoInventario, Inventario, Reservastock,
    AjusteInventario, AjusteInventarioDetalle,
)
# from erp.woocommerce_sync import actualizar_stock_woocommerce # Importación local para la tarea
from celery import shared_task


def calcular_stock_disponible(producto: Producto) -> int:
    """
    Stock realmente vendible de un producto simple: cantidad total menos las
    reservas vigentes (``Reservastock.valido_hasta`` en el futuro).

    ``Reservastock`` solo referencia ``Producto`` (no variantes), así que
    esta función no aplica a `Variacionproducto` -- para variantes se usa su
    `cantidad` directamente.
    """
    cantidad_total = producto.cantidad or 0
    reservado = Reservastock.objects.filter(
        producto=producto, valido_hasta__gt=timezone.now()
    ).aggregate(total=Sum("cantidad"))["total"] or 0
    return max(cantidad_total - reservado, 0)

@shared_task
def woocommerce_sync_task_celery(sku, nueva_cantidad):
    """
    Tarea de Celery para sincronizar stock con WooCommerce.
    """
    from erp.woocommerce_sync import actualizar_stock_woocommerce
    try:
        print(f"Sincronizando SKU: {sku} con cantidad: {nueva_cantidad}")
        actualizar_stock_woocommerce(sku=sku, nueva_cantidad=nueva_cantidad)
    except Exception as e:
        print(f"Error sincronizando {sku} con WooCommerce: {str(e)}")

def sincronizar_item_woocommerce(item):
    """
    Encola la sincronización con WooCommerce sin dejar que un broker caído
    (Redis/RabbitMQ no disponible) rompa la venta/pedido que llamó a esto.
    Esta función se invoca desde CADA reducción de stock (POS, catálogo
    público, pedidos B2B) -- antes, cualquier venta de un item con `sku` se
    caía con un 500 aunque el stock ya se hubiera descontado correctamente.
    """
    if hasattr(item, 'sku') and item.sku:
        from apps.core.tasks import dispatch_task
        dispatch_task(woocommerce_sync_task_celery, sku=item.sku, nueva_cantidad=item.cantidad)

@transaction.atomic
def reducir_stock_item(item, cantidad_a_reducir):
    """
    Reduce el stock de un Producto o Variante y dispara la sincronización.

    Vuelve a leer el item con ``select_for_update()`` dentro de la
    transacción: sin este bloqueo, dos descuentos concurrentes sobre el
    mismo item (ej. una venta de POS y un pedido público simultáneos)
    pueden leer el mismo ``stock_actual`` y producir una sobreventa
    (lost update).
    """
    modelo = type(item)
    item_bloqueado = modelo.objects.select_for_update().get(pk=item.pk)

    stock_actual = item_bloqueado.cantidad or 0
    if stock_actual < cantidad_a_reducir:
        raise ValueError(f"Stock insuficiente para el item {getattr(item_bloqueado, 'nombre', 'ID:'+str(item_bloqueado.id))}")

    item_bloqueado.cantidad = stock_actual - cantidad_a_reducir
    item_bloqueado.save(update_fields=['cantidad'])

    sincronizar_item_woocommerce(item_bloqueado)
    return item_bloqueado

@transaction.atomic
def restaurar_stock_item(item, cantidad_a_restaurar):
    """
    Restaura el stock (ej: al anular una factura) y sincroniza.

    Igual que ``reducir_stock_item``, bloquea la fila con
    ``select_for_update()`` para evitar lost updates concurrentes.
    """
    modelo = type(item)
    item_bloqueado = modelo.objects.select_for_update().get(pk=item.pk)

    item_bloqueado.cantidad = (item_bloqueado.cantidad or 0) + cantidad_a_restaurar
    item_bloqueado.save(update_fields=['cantidad'])

    sincronizar_item_woocommerce(item_bloqueado)
    return item_bloqueado

@transaction.atomic
def registrar_movimiento_manual(inventario_id, tipo_movimiento, cantidad_afectada, usuario):
    """
    Lógica para cuando un administrador hace un ingreso o salida manual.
    """
    inventario = Inventario.objects.get(id=inventario_id)
    producto = inventario.producto
    
    # 1. Crear el registro de auditoría
    movimiento = MovimientoInventario.objects.create(
        inventario=inventario,
        tipo_movimiento=tipo_movimiento,
        producto=producto,
        cantidad_movida=cantidad_afectada,
    )
    
    # 2. Afectar el stock real
    if tipo_movimiento == 'entrada':
        restaurar_stock_item(producto, cantidad_afectada)
    elif tipo_movimiento == 'salida':
        reducir_stock_item(producto, cantidad_afectada)

    return movimiento


@transaction.atomic
def crear_y_aplicar_ajuste(*, usuario, detalles_data, **header_fields):
    """
    Crea un ``AjusteInventario`` (cabecera + líneas) y aplica de una vez el
    movimiento de stock de cada línea -- pensado para el caso de "el
    proveedor me dio una nota de entrega, no una factura" o una corrección
    tras un conteo físico, donde varias líneas de productos entran/salen
    juntas en un solo documento.

    Todo corre en una sola transacción: si una línea falla (ej. stock
    insuficiente para una salida), NINGUNA línea queda aplicada ni se crea
    el ajuste -- evita dejar un ajuste a medio aplicar con solo algunos
    productos movidos.
    """
    ajuste = AjusteInventario.objects.create(usuario=usuario, **header_fields)

    inventarios_cache: dict[tuple[int, int | None], Inventario] = {}

    for detalle_data in detalles_data:
        detalle = AjusteInventarioDetalle.objects.create(ajuste=ajuste, **detalle_data)
        item = detalle.variante or detalle.producto

        if ajuste.tipo == 'entrada':
            item_actualizado = restaurar_stock_item(item, detalle.cantidad)
        else:
            item_actualizado = reducir_stock_item(item, detalle.cantidad)

        detalle.stock_resultante = item_actualizado.cantidad
        detalle.save(update_fields=['stock_resultante'])

        # Deja también el registro en el kardex existente (`MovimientoInventario`),
        # para que este ajuste aparezca junto a los demás movimientos de stock.
        if detalle.producto_id:
            cache_key = (detalle.producto_id, ajuste.almacen_id)
            inventario = inventarios_cache.get(cache_key)
            if inventario is None:
                inventario, _ = Inventario.objects.get_or_create(
                    producto_id=detalle.producto_id, almacen_id=ajuste.almacen_id,
                    defaults={'cantidad': 0},
                )
                inventarios_cache[cache_key] = inventario
            MovimientoInventario.objects.create(
                inventario=inventario,
                tipo_movimiento=ajuste.tipo,
                producto_id=detalle.producto_id,
                cantidad_movida=detalle.cantidad,
            )

    return ajuste