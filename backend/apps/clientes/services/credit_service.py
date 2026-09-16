"""
Línea de crédito visible para el cliente B2B.

`ClienteB2B.limite_credito` existía desde el modelo original pero nada lo
leía ni lo validaba -- cualquier cliente podía acumular pedidos 'pendiente'
sin límite. Este servicio calcula cuánto de ese cupo ya está comprometido
en pedidos sin pagar, y lo usa para bloquear nuevos pedidos que se pasen.

`limite_credito == 0` se interpreta como "todavía no se configuró línea de
crédito para este cliente" y NO restringe nada (preserva el comportamiento
histórico para clientes ya existentes, que por defecto tienen 0).
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from apps.facturacion.models import Factura

from ..models import ClienteB2B


def credito_usado(cliente_b2b: ClienteB2B) -> Decimal:
    """Suma de `Factura.total` de pedidos del cliente aún no pagados."""
    total = Factura.objects.filter(cliente_b2b=cliente_b2b, estado="pendiente").aggregate(
        suma=Sum("total")
    )["suma"]
    return total or Decimal("0.00")


def credito_disponible(cliente_b2b: ClienteB2B) -> Decimal | None:
    """
    Cupo restante, o `None` si el cliente no tiene línea de crédito
    configurada (`limite_credito == 0`) -- en ese caso no hay límite que
    reportar ni que hacer cumplir.
    """
    if not cliente_b2b.limite_credito:
        return None
    return cliente_b2b.limite_credito - credito_usado(cliente_b2b)
