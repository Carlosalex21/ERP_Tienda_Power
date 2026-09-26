"""
Nivel de precio automático por volumen de compra.

En vez de que un vendedor asigne manualmente el `NivelPrecio` de un
`ClienteB2B` una vez y lo olvide, este servicio revisa cuánto compró el
cliente en el período de evaluación y lo SUBE de nivel automáticamente
cuando su historial ya califica para uno mejor -- "sube de categoría sin
que nadie lo gestione a mano".

Deliberadamente solo sube de nivel, nunca baja: un mes flojo de compras no
debe penalizar a un cliente con condiciones peores sin que un humano lo
decida. Bajar de nivel sigue siendo una acción manual del admin.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.facturacion.models import Factura
from apps.reportes.core.moneda_reporte import moneda_de_montos_comerciales, monto_documento

from ..models import ClienteB2B, NivelPrecio

PERIODO_EVALUACION_MESES = 3

# Un pedido "pendiente" ya demuestra volumen real de compra (el cliente lo
# hizo, se le reservó/entregó mercancía) aunque todavía no se haya
# conciliado el pago -- no tiene sentido hacerlo esperar a que su propia
# factura se marque pagada para que el sistema reconozca ese volumen.
ESTADOS_QUE_CUENTAN = ("pendiente", "pagado")


def total_comprado_periodo(cliente_b2b: ClienteB2B, meses: int = PERIODO_EVALUACION_MESES) -> Decimal:
    """
    Compras del cliente en los últimos `meses` meses, en la moneda de los
    umbrales de `NivelPrecio` (ver `moneda_de_montos_comerciales`) y sin
    mezclar facturas de monedas distintas.
    """
    desde = timezone.now() - timedelta(days=30 * meses)
    total = Factura.objects.filter(
        cliente_b2b=cliente_b2b,
        estado__in=ESTADOS_QUE_CUENTAN,
        fecha_operacion__gte=desde,
    ).aggregate(suma=Sum(monto_documento(moneda_de_montos_comerciales())))["suma"]
    return Decimal(total or 0).quantize(Decimal("0.01"))


def proximo_nivel(cliente_b2b: ClienteB2B) -> dict | None:
    """
    Info del siguiente nivel al que puede aspirar el cliente y cuánto le
    falta comprar en el período para alcanzarlo (para mostrarle progreso).
    """
    umbral_actual = cliente_b2b.nivel_precio.monto_minimo_periodo if cliente_b2b.nivel_precio else Decimal("0.00")
    siguiente = (
        NivelPrecio.objects.filter(activo=True, monto_minimo_periodo__gt=umbral_actual)
        .order_by("monto_minimo_periodo")
        .first()
    )
    if not siguiente:
        return None
    comprado = total_comprado_periodo(cliente_b2b)
    faltante = max(siguiente.monto_minimo_periodo - comprado, Decimal("0.00"))
    return {"nivel": siguiente, "monto_faltante": faltante}


def recalcular_nivel_precio(cliente_b2b: ClienteB2B) -> NivelPrecio | None:
    """
    Sube el `nivel_precio` del cliente si su historial de compra ya
    califica para un nivel con un umbral mayor al actual.

    Returns:
        El nuevo `NivelPrecio` si hubo upgrade, o `None` si no cambió.
    """
    total = total_comprado_periodo(cliente_b2b)
    umbral_actual = cliente_b2b.nivel_precio.monto_minimo_periodo if cliente_b2b.nivel_precio else Decimal("0.00")

    mejor_nivel = (
        NivelPrecio.objects.filter(activo=True, monto_minimo_periodo__lte=total)
        .order_by("-monto_minimo_periodo")
        .first()
    )
    if mejor_nivel and mejor_nivel.monto_minimo_periodo > umbral_actual:
        cliente_b2b.nivel_precio = mejor_nivel
        cliente_b2b.nivel_precio_actualizado_en = timezone.now()
        cliente_b2b.save(update_fields=["nivel_precio", "nivel_precio_actualizado_en"])
        return mejor_nivel
    return None
