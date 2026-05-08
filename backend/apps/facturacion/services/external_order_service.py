from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.facturacion.models import Orden, Factura, Detallefactura
from apps.inventario.models import Producto, Variacionproducto # Idealmente de apps.inventario.models en el futuro
from apps.inventario.services.stock_service import reducir_stock_item
from apps.core.notifications import NotificationService
import logging

logger = logging.getLogger(__name__)

@transaction.atomic
def create_external_order(cart_items, tenant, email_contacto=None, direccion=None):
    """
    Recibe una lista de items del carrito y crea una orden en estado 'pendiente'.
    cart_items = [{"codigo_barras": "1234", "cantidad": 2}, ...]
    """
    if not cart_items:
        raise ValueError("El carrito está vacío.")

    # 1. Crear la Orden
    orden = Orden.objects.create(
        estado='pendiente',
        direccion_envio=direccion,
        subtotal=Decimal("0.00"),
        total=Decimal("0.00"),
        iva_total=Decimal("0.00")
    )

    # 2. Crear la Factura asociada (como estructura de detalle)
    factura = Factura.objects.create(
        orden=orden,
        estado='pendiente',
        fecha_operacion=timezone.now(),
        subtotal=Decimal("0.00"),
        total=Decimal("0.00"),
        iva_total=Decimal("0.00"),
        nombre_cliente_pendiente=email_contacto,
        comentario_pendiente="Pedido web externo"
    )

    subtotal_factura = Decimal("0.00")
    iva_factura = Decimal("0.00")

    # 3. Procesar cada item
    for item in cart_items:
        barcode = item.get('codigo_barras')
        cantidad = int(item.get('cantidad', 1))

        if cantidad <= 0:
            continue

        producto_base = None
        variante_encontrada = None
        precio_final = Decimal("0.00")

        # Buscar por código de barras
        try:
            variante_encontrada = Variacionproducto.objects.select_related('producto__configuracion_iva').get(codigo_barras=barcode)
            producto_base = variante_encontrada.producto
            precio_final = variante_encontrada.precio
            reducir_stock_item(variante_encontrada, cantidad)
        except Variacionproducto.DoesNotExist:
            try:
                producto_base = Producto.objects.select_related('configuracion_iva').get(codigo_barras=barcode, activo=True)
                precio_final = producto_base.precio
                reducir_stock_item(producto_base, cantidad)
            except Producto.DoesNotExist:
                raise ValueError(f"Producto no encontrado para el código: {barcode}")

        # Calcular totales por línea
        subtotal_linea = precio_final * cantidad
        
        # Calcular IVA (Simplificado asumiendo base imponible incluida en precio o a calcular)
        tasa_iva = Decimal("0.00")
        if producto_base.configuracion_iva:
            tasa_iva = producto_base.configuracion_iva.porcentaje_iva / Decimal("100")
        
        # Asumiendo que el precio final ya incluye IVA
        base_imponible = subtotal_linea / (Decimal("1") + tasa_iva)
        iva_linea = subtotal_linea - base_imponible

        Detallefactura.objects.create(
            factura=factura,
            producto=producto_base,
            variante=variante_encontrada,
            cantidad=cantidad,
            precio_unitario=precio_final,
            descuento=Decimal("0.00"),
            subtotal_linea=base_imponible,
            iva_linea=iva_linea,
            total_linea=subtotal_linea
        )

        subtotal_factura += base_imponible
        iva_factura += iva_linea

    # 4. Actualizar totales
    total_factura = subtotal_factura + iva_factura
    
    factura.subtotal = subtotal_factura
    factura.iva_total = iva_factura
    factura.total = total_factura
    factura.save()

    orden.subtotal = subtotal_factura
    orden.iva_total = iva_factura
    orden.total = total_factura
    orden.save()

    # 5. Notificar al dueño
    try:
        NotificationService.send_new_order_notification(
            tenant=tenant, 
            orden_id=orden.id, 
            total=orden.total
        )
    except Exception as e:
        logger.error(f"Fallo al enviar notificación: {str(e)}")

    return orden
