# apps/inventario/core/stock_service.py
from django.db import transaction
from apps.inventario.models import Producto, Variacionproducto, MovimientoInventario, Inventario
from erp.woocommerce_sync import actualizar_stock_woocommerce # Asegúrate de que esta ruta sea correcta

def sincronizar_item_woocommerce(item):
    """
    Servicio aislado para manejar la comunicación con WooCommerce.
    A futuro, aquí puedes implementar Celery (tareas en segundo plano)
    para que la venta no se quede esperando la respuesta de internet.
    """
    if hasattr(item, 'sku') and item.sku:
        try:
            print(f"Sincronizando SKU: {item.sku} con cantidad: {item.cantidad}")
            actualizar_stock_woocommerce(sku=item.sku, nueva_cantidad=item.cantidad)
        except Exception as e:
            # Aquí podrías guardar el error en un log para reintentar después
            print(f"Error sincronizando {item.sku} con WooCommerce: {str(e)}")

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