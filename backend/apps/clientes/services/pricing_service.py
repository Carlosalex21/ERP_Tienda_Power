"""
Servicio de precios: resuelve el precio efectivo de un producto según quién
lo está viendo.

Antes de este servicio, ``NivelPrecio.porcentaje_descuento`` se guardaba en
cada ``ClienteB2B`` pero nada lo aplicaba realmente sobre el precio de un
producto -- era un dato sembrado en el onboarding B2B sin ningún consumidor.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def calcular_precio_efectivo(item, cliente_b2b=None) -> Decimal:
    """
    Precio a mostrar/cobrar para un cliente concreto.

    Args:
        item: Instancia de ``apps.inventario.models.Producto`` o de
            ``apps.inventario.models.Variacionproducto`` (ambos exponen
            ``.precio``) -- un producto de tipo 'variable' se vende por
            variante/SKU, no por el precio del producto padre.
        cliente_b2b: Instancia de ``apps.clientes.models.ClienteB2B`` o
            ``None``. Sin cliente B2B (catálogo público / cliente retail),
            se devuelve el precio de lista tal cual.

    Returns:
        Decimal: precio de lista, o precio de lista menos el descuento del
        nivel de precio del cliente B2B.
    """
    precio_lista = item.precio or Decimal("0.00")
    if cliente_b2b is None or cliente_b2b.nivel_precio is None:
        return precio_lista

    descuento = cliente_b2b.nivel_precio.porcentaje_descuento or Decimal("0.00")
    precio_con_descuento = precio_lista * (Decimal("1") - descuento / Decimal("100"))
    return precio_con_descuento.quantize(CENT, rounding=ROUND_HALF_UP)
