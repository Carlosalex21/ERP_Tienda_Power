# apps/inventario/core/stock_service.py
from django.db import transaction
from apps.inventario.models import Producto, Variacionproducto, MovimientoInventario, Inventario
# from erp.woocommerce_sync import actualizar_stock_woocommerce # Importación local para la tarea
from celery import shared_task

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
    if hasattr(item, 'sku') and item.sku:
        woocommerce_sync_task_celery.delay(sku=item.sku, nueva_cantidad=item.cantidad)

@transaction.atomic
def reducir_stock_item(item, cantidad_a_reducir):
    """
    Reduce el stock de un Producto o Variante y dispara la sincronización.
    """
    stock_actual = item.cantidad or 0
    if stock_actual < cantidad_a_reducir:
        raise ValueError(f"Stock insuficiente para el item {getattr(item, 'nombre', 'ID:'+str(item.id))}")
    
    item.cantidad = stock_actual - cantidad_a_reducir
    item.save(update_fields=['cantidad'])
    
    sincronizar_item_woocommerce(item)
    return item

@transaction.atomic
def restaurar_stock_item(item, cantidad_a_restaurar):
    """
    Restaura el stock (ej: al anular una factura) y sincroniza.
    """
    item.cantidad = (item.cantidad or 0) + cantidad_a_restaurar
    item.save(update_fields=['cantidad'])
    
    sincronizar_item_woocommerce(item)
    return item

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
        cantidad=producto, # Asumiendo tu modelo actual
        # Aquí idealmente se guardaría la cantidad numérica del movimiento
    )
    
    # 2. Afectar el stock real
    if tipo_movimiento == 'entrada':
        restaurar_stock_item(producto, cantidad_afectada)
    elif tipo_movimiento == 'salida':
        reducir_stock_item(producto, cantidad_afectada)
        
    return movimiento