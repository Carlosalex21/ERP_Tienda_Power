from django.db import transaction
from apps.facturacion.models import Factura, Detallefactura
from django.utils import timezone
from apps.inventario.models import Variacionproducto
from apps.clientes.models import Cliente
from apps.inventario.services.stock_service import reducir_stock_item
from apps.configuracion.core.config_service import obtener_y_actualizar_correlativo
from .calculos_service import recalcular_y_guardar_factura

class OrderCreationError(Exception):
    pass

@transaction.atomic
def crear_orden_desde_pedido_publico(validated_data, usuario_sistema):
    """
    Crea una Factura y sus detalles a partir de un pedido del catálogo público.
    """
    # 1. Obtener o crear el cliente
    cliente, _ = Cliente.objects.get_or_create(
        telefono=validated_data['cliente_telefono'],
        defaults={'nombre': validated_data['cliente_nombre']}
    )

    # 2. Crear la cabecera de la factura
    factura = Factura.objects.create(
        cliente=cliente,
        usuario=usuario_sistema, # Un usuario genérico del sistema para pedidos públicos
        correlativo=obtener_y_actualizar_correlativo(),
        estado='pendiente', # El pedido debe ser confirmado por el admin
        fecha_operacion=timezone.now(),
        # Los totales se inicializan en 0 gracias a los defaults del modelo
    )

    # 3. Crear los detalles y reducir stock, sin calcular totales aquí
    for item_data in validated_data['items']:
        try:
            variacion = Variacionproducto.objects.select_related('producto').get(id=item_data['variacion_id'])
            reducir_stock_item(variacion, item_data['cantidad']) 
            Detallefactura.objects.create(
                factura=factura,
                producto=variacion.producto,
                variante=variacion, 
                cantidad=item_data['cantidad'],
                precio_unitario=variacion.precio 
            )
        except Variacionproducto.DoesNotExist:
            raise OrderCreationError(f"La variación con ID {item_data['variacion_id']} no existe.")
        except ValueError as e: # Error de stock insuficiente
            raise OrderCreationError(str(e))

    # 4. Delegar el cálculo de todos los totales al servicio especializado
    recalcular_y_guardar_factura(factura)
    
    return factura