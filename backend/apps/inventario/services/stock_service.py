# apps/inventario/core/stock_service.py
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from apps.inventario.models import (
    Producto, Variacionproducto, MovimientoInventario, Inventario, Reservastock,
    AjusteInventario, AjusteInventarioDetalle, TrasladoInventario, TrasladoInventarioDetalle,
)
# from erp.woocommerce_sync import actualizar_stock_woocommerce # Importación local para la tarea
from celery import shared_task

# Mismo umbral que usa `apps.reportes.core.dashboard_service` cuando un
# producto no tiene `stock_minimo` propio -- un solo lugar para no volver a
# desalinear el "bajo stock" del dashboard con el del Centro de Alertas.
UMBRAL_BAJO_STOCK_GENERAL = 10


def obtener_productos_bajo_stock():
    """
    Productos activos (no servicios) con stock por debajo de su
    `stock_minimo` propio, o del umbral general si no tienen uno definido --
    misma regla que ya usa el dashboard (`dashboard_service.py`), extraída
    aquí para que el Centro de Alertas no la reimplemente por tercera vez.
    """
    return list(
        Producto.objects.filter(activo=True).exclude(tipo='servicio').filter(
            Q(stock_minimo__isnull=False, cantidad__lt=F('stock_minimo')) |
            Q(stock_minimo__isnull=True, cantidad__lt=UMBRAL_BAJO_STOCK_GENERAL)
        ).order_by('cantidad').values('id', 'nombre', 'cantidad', 'stock_minimo')
    )


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

def _consumir_lotes_fefo(producto, cantidad_a_reducir) -> None:
    """
    Descuenta de los lotes ACTIVOS del producto, del que vence más pronto al
    que vence más tarde (FEFO -- first-expired-first-out), hasta agotar
    `cantidad_a_reducir` o quedarse sin lotes con saldo.

    No es estricto: el loteo siempre fue opcional (ver `apps.farmacia.models.
    LoteProducto`, antes solo usado por el vertical farmacia, ahora
    disponible para cualquiera) -- si el producto no tiene lotes registrados,
    o tiene menos unidades loteadas que las vendidas, el resto simplemente
    no queda atribuido a ningún lote. `Producto.cantidad` sigue siendo la
    única fuente de verdad del stock real; esto solo mantiene al día CUÁLES
    lotes específicos ya se vendieron, para la alerta de "por vencer".
    """
    try:
        from apps.farmacia.models import LoteProducto
    except Exception:
        return

    restante = cantidad_a_reducir
    lotes = LoteProducto.objects.select_for_update().filter(
        producto=producto, activo=True, cantidad__gt=0,
    ).order_by('fecha_vencimiento')
    for lote in lotes:
        if restante <= 0:
            break
        consumir = min(lote.cantidad, restante)
        lote.cantidad -= consumir
        lote.save(update_fields=['cantidad'])
        restante -= consumir


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

    # Aviso inmediato (Web Push) solo en la TRANSICIÓN a agotado (stock_actual
    # > 0 y el nuevo queda en 0 o menos) -- nunca en cada venta subsiguiente
    # de un producto que ya estaba en 0, que solo repetiría el mismo aviso
    # sin nada nuevo que decir. Aislado con try/except: nunca debe poder
    # tumbar la venta/ajuste que disparó este descuento de stock.
    if stock_actual > 0 and item_bloqueado.cantidad <= 0:
        try:
            from apps.restaurantes.push_notifications import enviar_push_a_staff
            nombre_item = getattr(item_bloqueado, 'nombre', None) or f'Producto #{item_bloqueado.pk}'
            enviar_push_a_staff('Producto agotado', f'{nombre_item} se quedó sin stock.', url='/admin/inventario')
        except Exception:
            pass

    # Los lotes solo existen sobre `Producto` (no sobre variantes) -- ver
    # `apps.farmacia.models.LoteProducto`.
    if modelo is Producto:
        try:
            _consumir_lotes_fefo(item_bloqueado, cantidad_a_reducir)
        except Exception:
            import logging
            logging.getLogger(__name__).warning('No se pudo descontar de los lotes del producto %s', item_bloqueado.pk, exc_info=True)

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


def _actualizar_costo_promedio(item, cantidad_entrada, costo_unitario_entrada) -> None:
    """
    Recalcula el costo promedio ponderado de un Producto/Variante tras una
    ENTRADA con costo conocido -- promedia el valor de lo que ya había en
    stock con el valor de lo que entra, y lo guarda en `costo_promedio`.
    Se bloquea la fila (misma razón que `reducir_stock_item`): dos entradas
    concurrentes del mismo item no deben pisarse el promedio calculado.
    """
    modelo = type(item)
    item_bloqueado = modelo.objects.select_for_update().get(pk=item.pk)
    cantidad_previa = item_bloqueado.cantidad or 0
    costo_previo = item_bloqueado.costo_promedio or Decimal('0')
    nueva_cantidad_total = cantidad_previa + cantidad_entrada
    if nueva_cantidad_total <= 0:
        return
    valor_previo = Decimal(cantidad_previa) * Decimal(costo_previo)
    valor_entrada = Decimal(cantidad_entrada) * Decimal(str(costo_unitario_entrada))
    item_bloqueado.costo_promedio = (valor_previo + valor_entrada) / Decimal(nueva_cantidad_total)
    item_bloqueado.save(update_fields=['costo_promedio'])


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
            if detalle.costo_unitario:
                _actualizar_costo_promedio(item, detalle.cantidad, detalle.costo_unitario)
            item_actualizado = restaurar_stock_item(item, detalle.cantidad)
        else:
            item_actualizado = reducir_stock_item(item, detalle.cantidad)

        detalle.stock_resultante = item_actualizado.cantidad
        detalle.save(update_fields=['stock_resultante'])

        # Deja también el registro en el kardex existente (`MovimientoInventario`)
        # Y mantiene al día el desglose por almacén (`Inventario.cantidad`) --
        # antes esta línea solo creaba la fila si no existía, sin sumarle ni
        # restarle nada: el desglose por almacén quedaba congelado en 0 para
        # siempre, sin importar cuántos ajustes se aplicaran.
        if detalle.producto_id:
            cache_key = (detalle.producto_id, ajuste.almacen_id)
            inventario = inventarios_cache.get(cache_key)
            if inventario is None:
                inventario, _ = Inventario.objects.get_or_create(
                    producto_id=detalle.producto_id, almacen_id=ajuste.almacen_id,
                    defaults={'cantidad': 0},
                )
                inventarios_cache[cache_key] = inventario
            inventario_bloqueado = Inventario.objects.select_for_update().get(pk=inventario.pk)
            if ajuste.tipo == 'entrada':
                inventario_bloqueado.cantidad = (inventario_bloqueado.cantidad or 0) + detalle.cantidad
            else:
                inventario_bloqueado.cantidad = max((inventario_bloqueado.cantidad or 0) - detalle.cantidad, 0)
            inventario_bloqueado.save(update_fields=['cantidad'])
            inventarios_cache[cache_key] = inventario_bloqueado
            MovimientoInventario.objects.create(
                inventario=inventario_bloqueado,
                tipo_movimiento=ajuste.tipo,
                producto_id=detalle.producto_id,
                cantidad_movida=detalle.cantidad,
            )

    # Asiento contable automático -- OPCIONAL y completamente aislado, mismo
    # criterio que el de ventas (ver `pagos_service.py`): import local
    # porque `apps.inventario` es compartido por todas las verticales y no
    # debe depender de que `apps.contabilidad` esté instalada, y nunca debe
    # poder tumbar un ajuste que ya se aplicó sobre el stock real.
    try:
        from apps.contabilidad.services import generar_asiento_automatico_ajuste_inventario
        generar_asiento_automatico_ajuste_inventario(ajuste)
    except Exception:
        pass

    # Cuenta por pagar automática -- mismo criterio: OPCIONAL y aislado, solo
    # actúa si es una compra con proveedor y costo conocido (ver
    # `crear_cuenta_por_pagar_desde_ajuste`), nunca puede tumbar el ajuste
    # que ya se aplicó sobre el stock real.
    try:
        from apps.proveedores.core.proveedores_service import crear_cuenta_por_pagar_desde_ajuste
        crear_cuenta_por_pagar_desde_ajuste(ajuste)
    except Exception:
        pass

    return ajuste


@transaction.atomic
def crear_y_aplicar_traslado(*, usuario, almacen_origen_id, almacen_destino_id, detalles_data, observaciones=''):
    """
    Crea un traslado de stock entre dos almacenes y lo aplica de inmediato
    -- a propósito NO hay un estado "en tránsito" a la espera de que alguien
    confirme la recepción en el otro almacén: al guardarse, ya se descontó
    del origen y se sumó al destino, en la misma transacción. Si una línea
    falla (ej. no hay suficiente stock de ese producto en el origen),
    NINGUNA línea queda aplicada ni se crea el traslado (mismo criterio que
    `crear_y_aplicar_ajuste`).

    El total global de stock de cada producto (`Producto.cantidad`, lo que
    de verdad determina si se puede vender) NO cambia -- un traslado solo
    mueve DÓNDE físicamente está ese stock (`Inventario` por almacén), no
    cuánto hay en total.
    """
    if almacen_origen_id == almacen_destino_id:
        raise ValueError("El almacén de origen y destino no pueden ser el mismo.")

    traslado = TrasladoInventario.objects.create(
        usuario=usuario, almacen_origen_id=almacen_origen_id, almacen_destino_id=almacen_destino_id,
        observaciones=observaciones,
    )

    for detalle_data in detalles_data:
        producto_id = detalle_data['producto_id']
        cantidad = detalle_data['cantidad']

        origen, _ = Inventario.objects.get_or_create(
            producto_id=producto_id, almacen_id=almacen_origen_id, defaults={'cantidad': 0},
        )
        origen_bloqueado = Inventario.objects.select_for_update().get(pk=origen.pk)
        disponible = origen_bloqueado.cantidad or 0
        if disponible < cantidad:
            producto_nombre = Producto.objects.filter(pk=producto_id).values_list('nombre', flat=True).first() or f"ID {producto_id}"
            raise ValueError(
                f"No hay suficiente stock de '{producto_nombre}' en el almacén de origen "
                f"(disponible: {disponible}, solicitado: {cantidad})."
            )
        origen_bloqueado.cantidad = disponible - cantidad
        origen_bloqueado.save(update_fields=['cantidad'])

        destino, _ = Inventario.objects.get_or_create(
            producto_id=producto_id, almacen_id=almacen_destino_id, defaults={'cantidad': 0},
        )
        destino_bloqueado = Inventario.objects.select_for_update().get(pk=destino.pk)
        destino_bloqueado.cantidad = (destino_bloqueado.cantidad or 0) + cantidad
        destino_bloqueado.save(update_fields=['cantidad'])

        TrasladoInventarioDetalle.objects.create(
            traslado=traslado, producto_id=producto_id, cantidad=cantidad,
            stock_resultante_origen=origen_bloqueado.cantidad,
            stock_resultante_destino=destino_bloqueado.cantidad,
        )
        MovimientoInventario.objects.create(
            inventario=origen_bloqueado, tipo_movimiento='salida', producto_id=producto_id, cantidad_movida=cantidad,
        )
        MovimientoInventario.objects.create(
            inventario=destino_bloqueado, tipo_movimiento='entrada', producto_id=producto_id, cantidad_movida=cantidad,
        )

    return traslado