from django.db import transaction
from ..models import Factura
from apps.inventario.services.stock_service import restaurar_stock_item

class FacturaAnulacionError(Exception):
    pass

@transaction.atomic
def anular_factura_y_restaurar_stock(factura_id: int):
    """
    Anula una factura y restaura el stock de todos sus detalles.

    Solo restaura si `inventario_afectado` está en `True` -- un 'borrador'
    (o una nota de entrega recién creada que se anula antes de convertirse)
    puede no haber descontado nada todavía, y restaurar en ese caso
    inflaría el stock con unidades que nunca salieron.
    """
    factura = Factura.objects.select_related().get(pk=factura_id)
    if factura.estado == 'anulada':
        raise FacturaAnulacionError("La factura ya ha sido anulada.")

    if factura.inventario_afectado:
        for detalle in factura.detalles.select_related('producto', 'variante', 'presentacion').all():
            # Prioriza restaurar el stock de la variación si existe, si no, usa el producto.
            item_a_restaurar = detalle.variante if detalle.variante else detalle.producto
            # Simétrico a `afectar_inventario_por_venta`: una línea con
            # presentación se descontó multiplicada por su factor, así que
            # se restaura multiplicada igual -- si no, "anular" una venta de
            # "2 Bulto x12" solo devolvía 2 unidades base en vez de 24.
            cantidad_base = detalle.cantidad
            if detalle.presentacion is not None:
                cantidad_base = detalle.cantidad * detalle.presentacion.factor_conversion
            restaurar_stock_item(item_a_restaurar, cantidad_base)
        factura.inventario_afectado = False

    factura.estado = 'anulada'
    factura.save(update_fields=['estado', 'inventario_afectado'])
    return factura