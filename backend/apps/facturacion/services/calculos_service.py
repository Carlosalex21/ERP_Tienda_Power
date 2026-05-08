from decimal import Decimal, ROUND_HALF_UP
from django.db.models import F
from apps.facturacion.models import Detallefactura # Ajustar importación según tu estructura

def recalcular_y_guardar_factura(factura):
    """
    Recalcula subtotales, IVA y totales de la factura y sus detalles.
    """
    detalles = Detallefactura.objects.filter(factura=factura).select_related(
        'producto__configuracion_iva',
        'variante__producto__configuracion_iva'
    )
    
    total_factura_subtotal = Decimal("0.00")
    total_factura_iva = Decimal("0.00")
    detalles_a_actualizar = []

    for detalle in detalles:
        precio_final_unitario = detalle.precio_unitario
        descuento_porcentaje = detalle.descuento or Decimal("0.00")
        total_linea_con_descuento = (precio_final_unitario * detalle.cantidad) * (Decimal("1") - descuento_porcentaje / Decimal("100"))
        
        tasa_iva = Decimal("0.00")
        if detalle.producto.configuracion_iva:
            tasa_iva = Decimal(detalle.producto.configuracion_iva.porcentaje_iva) / Decimal("100")
        
        if tasa_iva > 0:
            subtotal_linea = (total_linea_con_descuento / (Decimal("1") + tasa_iva))
        else:
            subtotal_linea = total_linea_con_descuento

        iva_linea = total_linea_con_descuento - subtotal_linea
        
        detalle.subtotal_linea = subtotal_linea.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        detalle.iva_linea = iva_linea.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        detalle.total_linea = total_linea_con_descuento.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        detalles_a_actualizar.append(detalle)
        total_factura_subtotal += detalle.subtotal_linea
        total_factura_iva += detalle.iva_linea
    
    if detalles_a_actualizar:
        Detallefactura.objects.bulk_update(detalles_a_actualizar, ['subtotal_linea', 'iva_linea', 'total_linea'])

    factura.subtotal = total_factura_subtotal
    factura.iva_total = total_factura_iva
    factura.total = total_factura_subtotal + total_factura_iva
    factura.save()