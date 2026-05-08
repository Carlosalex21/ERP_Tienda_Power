from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.facturacion.models import Factura, Detallefactura
from apps.inventario.models import Variacionproducto, Producto
from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura

@transaction.atomic
def agg_producto_a_orden_service(usuario, cliente_id, barcode, cantidad=1, descuento_linea=None, eliminar=False):
    """
    Lógica core para agregar un producto al carrito/factura.
    Devuelve una tupla: (factura_instancia, mensaje_error)
    """
    producto_base = None
    variante_encontrada = None
    precio_final = Decimal("0.00")
    stock_disponible = 0
    
    try:
        variante_encontrada = Variacionproducto.objects.select_related('producto__configuracion_iva').get(codigo_barras=barcode)
        producto_base = variante_encontrada.producto
        precio_final = variante_encontrada.precio
        stock_disponible = variante_encontrada.cantidad or 0
    except Variacionproducto.DoesNotExist:
        try:
            producto_base = Producto.objects.select_related('configuracion_iva').get(codigo_barras=barcode, activo=True)
            precio_final = producto_base.precio
            stock_disponible = producto_base.cantidad or 0
        except Producto.DoesNotExist:
            return None, "Producto no encontrado para este código."

    factura, _ = Factura.objects.get_or_create(
        cliente_id=cliente_id, 
        estado="abierta", 
        fecha_operacion__date=timezone.now().date(),
        defaults={
            'usuario': usuario, 
            'fecha_operacion': timezone.now(), 
            'subtotal': Decimal("0.00"), 
            'descuento_global': Decimal("0.00"), 
            'iva_total': Decimal("0.00"), 
            'total': Decimal("0.00"), 
            'activo': True
        }
    )
    
    filtro_detalle = {'factura': factura, 'producto': producto_base}
    if variante_encontrada:
        filtro_detalle['variante'] = variante_encontrada
    detalle_existente = Detallefactura.objects.filter(**filtro_detalle).first()
    
    if eliminar and detalle_existente:
        detalle_existente.delete()
    elif not eliminar:
        cantidad_en_orden = detalle_existente.cantidad if detalle_existente else 0
        if (cantidad + cantidad_en_orden > stock_disponible):
            return None, f"La cantidad total excede el stock disponible ({stock_disponible})."
        
        if detalle_existente:
            detalle_existente.cantidad += cantidad
            if detalle_existente.cantidad <= 0:
                detalle_existente.delete()
            else:
                if descuento_linea is not None:
                    detalle_existente.descuento = Decimal(descuento_linea)
                detalle_existente.save()
        elif cantidad > 0:
            Detallefactura.objects.create(
                factura=factura, producto=producto_base, variante=variante_encontrada,
                cantidad=cantidad, precio_unitario=precio_final,
                descuento=Decimal(descuento_linea or "0.00"),
                subtotal_linea=Decimal("0.00"), iva_linea=Decimal("0.00"), total_linea=Decimal("0.00")
            )

    recalcular_y_guardar_factura(factura)
    return factura, None