from django.db import transaction
from apps.facturacion.models import Factura, Detallefactura
from django.utils import timezone
from apps.inventario.models import PresentacionProducto, Producto, Variacionproducto
from apps.clientes.models import Cliente
from apps.inventario.services.stock_service import reducir_stock_item
from apps.configuracion.services.conversion_service import get_tasa_vigente, get_moneda_base, convertir
from apps.pagos.models import MetodoPagoConfig, TransaccionPasarela
from .calculos_service import recalcular_y_guardar_factura

class OrderCreationError(Exception):
    pass

def crear_orden_desde_pedido_publico(validated_data, usuario_sistema):
    """
    Crea una Factura y sus detalles a partir de un pedido del catálogo público.

    Cada ``item`` siempre trae ``producto_id`` (el producto base, tal como lo
    expone ``PublicProductoSerializer``) y, opcionalmente, ``variante_id``
    y/o ``presentacion_id`` -- ambos deben pertenecer a ESE producto, si no
    se rechaza el pedido completo (ver validación abajo).
    """
    # Calienta la tasa de cambio ANTES de abrir la transacción. Para tenants
    # venezolanos, `get_tasa_vigente('USD')` puede disparar (una vez al día,
    # por proceso) una consulta HTTP real al BCV (hasta ~6s) -- si eso
    # corriera DENTRO del `atomic()` de abajo, lo haría mientras se tiene
    # bloqueada con `select_for_update()` la fila única del correlativo
    # (ver `obtener_y_actualizar_correlativo`), serializando literalmente
    # cualquier otro checkout del catálogo público detrás de esta petición.
    # Aquí, fuera de toda transacción/lock, no bloquea a nadie más.
    try:
        get_tasa_vigente('USD')
    except Exception:
        pass  # Si de verdad hace falta una tasa y no hay, fallará más abajo con un error claro.

    # Moneda base del tenant: los pedidos del catálogo se registran SIEMPRE
    # en ella (ver más abajo la conversión de `precio_unitario`) -- así la
    # factura resultante es consistente con cualquier otra del sistema y
    # `recalcular_y_guardar_factura` puede consolidar sus totales en base sin
    # tratarla como un caso especial.
    moneda_base = get_moneda_base()

    with transaction.atomic():
        # 1. Obtener o crear el cliente
        cliente, _ = Cliente.objects.get_or_create(
            telefono=validated_data['cliente_telefono'],
            defaults={'nombre': validated_data['cliente_nombre']}
        )

        # 2. Crear la cabecera de la factura. `registrar_libro=False`: en
        # este punto los totales son todavía 0 (se calculan en el paso 4),
        # así que registrarla ahora en el Libro de Ventas solo produciría una
        # línea con montos en cero que el guardado del paso 4 reescribiría de
        # inmediato -- una consulta+escritura de por medio sin ningún valor.
        # No se le asigna `correlativo` aquí: `pendiente_de_aprobacion=True`
        # hace que `Factura.save()` NO le genere correlativo ni número de
        # control todavía -- este pedido puede ser rechazado por el admin, y
        # hasta que no lo confirme no debe "quemar" numeración fiscal.
        factura = Factura(
            cliente=cliente,
            usuario=usuario_sistema, # Un usuario genérico del sistema para pedidos públicos
            estado='pendiente', # El pedido debe ser confirmado por el admin
            pendiente_de_aprobacion=True,
            moneda=moneda_base,
            fecha_operacion=timezone.now(),
            # Los totales se inicializan en 0 gracias a los defaults del modelo
        )
        factura.save(registrar_libro=False)

        # 3. Resolver todos los productos del carrito en una sola consulta
        # (antes: un `Producto.objects.get()` por línea) y crear los
        # detalles en un solo INSERT con `bulk_create` (antes: un `.create()`
        # por línea). La reducción de stock sigue siendo por línea -- cada
        # una necesita su propio `select_for_update()` para no perder una
        # venta concurrente sobre el mismo producto (ver `stock_service`).
        producto_ids = [item['producto_id'] for item in validated_data['items']]
        productos_por_id = {
            p.id: p for p in Producto.objects.select_related('moneda').filter(id__in=producto_ids, disponible_online=True)
        }
        variante_ids = [item['variante_id'] for item in validated_data['items'] if item.get('variante_id')]
        variantes_por_id = {v.id: v for v in Variacionproducto.objects.filter(id__in=variante_ids, activo=True)}
        presentacion_ids = [item['presentacion_id'] for item in validated_data['items'] if item.get('presentacion_id')]
        presentaciones_por_id = {
            p.id: p for p in PresentacionProducto.objects.filter(id__in=presentacion_ids, activo=True)
        }

        detalles_a_crear = []
        for item_data in validated_data['items']:
            producto = productos_por_id.get(item_data['producto_id'])
            if producto is None:
                raise OrderCreationError(f"El producto con ID {item_data['producto_id']} no existe o no está disponible.")

            variante = None
            variante_id = item_data.get('variante_id')
            if variante_id:
                variante = variantes_por_id.get(variante_id)
                if variante is None or variante.producto_id != producto.id:
                    raise OrderCreationError(f"La variante seleccionada para '{producto.nombre}' ya no está disponible.")

            presentacion = None
            presentacion_id = item_data.get('presentacion_id')
            if presentacion_id:
                presentacion = presentaciones_por_id.get(presentacion_id)
                if presentacion is None or presentacion.producto_id != producto.id:
                    raise OrderCreationError(f"La presentación seleccionada para '{producto.nombre}' ya no está disponible.")

            # Igual que en `afectar_inventario_por_venta`: la presentación
            # convierte "cuántas de esta presentación" a unidades base antes
            # de descontar stock; una variante tiene su propio stock directo,
            # sin conversión (nunca coexisten variante y presentación).
            item_para_stock = variante if variante is not None else producto
            cantidad_base = item_data['cantidad']
            if presentacion is not None:
                cantidad_base = item_data['cantidad'] * presentacion.factor_conversion
            try:
                reducir_stock_item(item_para_stock, cantidad_base)
            except ValueError as e:  # Error de stock insuficiente
                raise OrderCreationError(str(e))

            # `producto.precio` puede estar expresado en la moneda propia del
            # producto (`producto.moneda`), no necesariamente en la moneda
            # base del tenant -- copiarlo tal cual (como antes) dejaba un
            # monto, por ejemplo, en USD guardado como si fuera Bs, sin
            # ninguna conversión real (`factura.moneda` nunca se seteaba, así
            # que `recalcular_y_guardar_factura` lo trataba como "ya está en
            # base" y no corregía nada). Si el producto no tiene moneda
            # asignada, ya se asume en la moneda base (mismo criterio que
            # usa el resto del sistema, ver `Producto.moneda`). El precio
            # base sale de la presentación (si se eligió) o de la variante
            # (si tiene uno propio) antes de convertir.
            if presentacion is not None:
                precio_unitario = presentacion.precio if presentacion.precio is not None else (producto.precio or 0) * presentacion.factor_conversion
            elif variante is not None and variante.precio is not None:
                precio_unitario = variante.precio
            else:
                precio_unitario = producto.precio or 0
            if producto.moneda_id and producto.moneda.codigo != moneda_base.codigo:
                precio_unitario = convertir(precio_unitario, producto.moneda.codigo, moneda_base.codigo)
            detalles_a_crear.append(Detallefactura(
                factura=factura,
                producto=producto,
                variante=variante,
                presentacion=presentacion,
                cantidad=item_data['cantidad'],
                precio_unitario=precio_unitario,
            ))
        Detallefactura.objects.bulk_create(detalles_a_crear)

        # 4. Delegar el cálculo de todos los totales al servicio especializado
        # (este guardado de la factura es el que de verdad registra la línea
        # en el Libro de Ventas, ya con los totales finales).
        recalcular_y_guardar_factura(factura)

        # 5. Si el cliente ya indicó cómo pagó (Pago Móvil/Zelle + referencia),
        # dejamos registrada la transacción de pasarela de una vez -- así el
        # admin no tiene que cruzar a mano "este pedido" con "este comprobante".
        metodo_pago_config_id = validated_data.get('metodo_pago_config_id')
        referencia_pago = validated_data.get('referencia_pago')
        if metodo_pago_config_id:
            metodo_pago = MetodoPagoConfig.objects.filter(id=metodo_pago_config_id, activo=True).first()
            if metodo_pago:
                TransaccionPasarela.objects.create(
                    factura=factura,
                    metodo_pago=metodo_pago,
                    monto=factura.total,
                    referencia_externa=referencia_pago or '',
                    estado='pendiente',
                )

        return factura
