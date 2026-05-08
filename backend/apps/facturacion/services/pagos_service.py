import uuid
from django.db import transaction
from django.utils import timezone
from apps.facturacion.models import Factura, MetodoPago, Detallefactura, Transaccionpago
from apps.inventario.services.stock_service import reducir_stock_item

def afectar_inventario_por_venta(factura):
    """
    Recorre los detalles de la factura y delega la reducción de stock
    al servicio especializado del módulo de inventario.
    """
    detalles = Detallefactura.objects.select_related('producto', 'variante').filter(factura=factura)
    for detalle in detalles:
        # Determinamos si vendimos una variante específica o el producto base
        item_vendido = detalle.variante if detalle.variante else detalle.producto
        reducir_stock_item(item_vendido, detalle.cantidad)


@transaction.atomic
def procesar_pago_factura_service(factura_id, metodo_pago_id, monto_recibido, estado_override, datos_adicionales):
    """
    Lógica core transaccional para registrar el pago de una factura.
    Levanta excepciones (ValueError) si hay reglas de negocio rotas.
    """
    try:
        metodo = MetodoPago.objects.get(id=metodo_pago_id)
        factura = Factura.objects.select_for_update().get(id=factura_id, estado="abierta")
    except MetodoPago.DoesNotExist:
        raise ValueError("Método de pago no encontrado.")
    except Factura.DoesNotExist:
        raise ValueError("Factura no encontrada o ya procesada.")

    # Lógica "Pagar luego"
    if metodo.tipo_metodo == "Pagar luego" or estado_override == "pendiente":
        # Llamamos a nuestra función limpia
        afectar_inventario_por_venta(factura)
        
        factura.metodo_pago = metodo
        factura.estado = "pendiente"
        factura.nombre_cliente_pendiente = datos_adicionales.get("nombre_cliente", "")
        factura.comentario_pendiente = datos_adicionales.get("comentario", "")
        factura.save()
        return factura, None

    # Lógica Pago Completo
    if monto_recibido is None or float(monto_recibido) < float(factura.total):
        raise ValueError(f"Monto insuficiente. Se requiere {factura.total}")

    # Llamamos a nuestra función limpia
    afectar_inventario_por_venta(factura)
    
    factura.metodo_pago = metodo
    factura.estado = "pagado"
    factura.fecha_pago = timezone.now()
    factura.save()

    # Registro de la transacción
    transaccion = Transaccionpago.objects.create(
        orden=factura.orden, # Enlazando si existe orden
        monto=factura.total,
        metodo_pago=metodo,
        estado="exitoso",
        codigo_transaccion=str(uuid.uuid4()),
        fecha=timezone.now(),
        activo=True
    )
    
    return factura, transaccion