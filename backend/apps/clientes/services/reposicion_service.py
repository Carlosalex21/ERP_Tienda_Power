"""
Reposición predictiva para clientes B2B.

No conocemos el stock real del cliente (eso vive en SU almacén, no en el
del tenant), así que en vez de eso proyectamos su propio ritmo histórico de
recompra: cada cuántos días vuelve a pedir un producto y cuánto pide, para
avisarle "a este ritmo se te acaba en N días" y ofrecerle repetir ese
pedido con un clic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Max, Min, Sum
from django.utils import timezone

from apps.facturacion.models import Detallefactura
from apps.inventario.models import Producto

from ..models import ClienteB2B

# Un producto necesita al menos 2 pedidos distintos en su historial para
# poder calcular un intervalo promedio entre compras -- con 1 solo pedido
# no hay ritmo que proyectar.
MINIMO_PEDIDOS_PARA_PROYECTAR = 2

# "Urgente" = se proyecta que ya debería haber repuesto, o le quedan pocos días.
UMBRAL_DIAS_URGENTE = 3


@dataclass
class SugerenciaReposicion:
    producto: Producto
    cantidad_habitual: int
    dias_entre_pedidos: float
    ultima_compra: date
    dias_estimados_restantes: int
    urgente: bool


def calcular_sugerencias_reposicion(
    cliente_b2b: ClienteB2B, minimo_pedidos: int = MINIMO_PEDIDOS_PARA_PROYECTAR
) -> list[SugerenciaReposicion]:
    """
    Para cada producto que el cliente ya compró al menos `minimo_pedidos`
    veces, calcula el intervalo promedio entre pedidos y proyecta cuántos
    días faltan (puede ser negativo: ya se pasó) desde su última compra.
    """
    filas = (
        Detallefactura.objects.filter(factura__cliente_b2b=cliente_b2b, producto__isnull=False)
        .values("producto_id")
        .annotate(
            veces_comprado=Count("factura_id", distinct=True),
            cantidad_total=Sum("cantidad"),
            primera_compra=Min("factura__fecha_operacion"),
            ultima_compra=Max("factura__fecha_operacion"),
        )
        .filter(veces_comprado__gte=minimo_pedidos)
    )

    productos_por_id = {p.id: p for p in Producto.objects.filter(id__in=[f["producto_id"] for f in filas])}

    hoy = timezone.now().date()
    sugerencias: list[SugerenciaReposicion] = []
    for fila in filas:
        producto = productos_por_id.get(fila["producto_id"])
        if producto is None:
            continue

        primera = fila["primera_compra"].date()
        ultima = fila["ultima_compra"].date()
        dias_totales = (ultima - primera).days
        intervalos = fila["veces_comprado"] - 1
        if intervalos <= 0 or dias_totales <= 0:
            continue

        dias_entre_pedidos = dias_totales / intervalos
        cantidad_habitual = round(fila["cantidad_total"] / fila["veces_comprado"])
        dias_desde_ultima = (hoy - ultima).days
        dias_estimados_restantes = round(dias_entre_pedidos - dias_desde_ultima)

        sugerencias.append(
            SugerenciaReposicion(
                producto=producto,
                cantidad_habitual=max(cantidad_habitual, 1),
                dias_entre_pedidos=round(dias_entre_pedidos, 1),
                ultima_compra=ultima,
                dias_estimados_restantes=dias_estimados_restantes,
                urgente=dias_estimados_restantes <= UMBRAL_DIAS_URGENTE,
            )
        )

    sugerencias.sort(key=lambda s: s.dias_estimados_restantes)
    return sugerencias
