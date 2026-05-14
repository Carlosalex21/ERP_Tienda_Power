from django.db import transaction
from ..models import Factura
from apps.inventario.services.stock_service import restaurar_stock_item

class FacturaAnulacionError(Exception):
    pass

@transaction.atomic
def anular_factura_y_restaurar_stock(factura_id: int):
    """
    Anula una factura y restaura el stock de todos sus detalles.
    """
    factura = Factura.objects.get(pk=factura_id)
    if factura.estado == 'anulada':
        raise FacturaAnulacionError("La factura ya ha sido anulada.")

    for detalle in factura.detalles.all():
        # Prioriza restaurar el stock de la variación si existe, si no, usa el producto.
        item_a_restaurar = detalle.variante if detalle.variante else detalle.producto
        restaurar_stock_item(item_a_restaurar, detalle.cantidad)
    
    factura.estado = 'anulada'
    factura.save(update_fields=['estado'])
    return factura