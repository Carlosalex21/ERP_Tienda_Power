"""
Moneda en la que se expresan los reportes y el dashboard.

El usuario puede ver todo en la moneda BASE del tenant (ej. Bs.) o en la de
REFERENCIA (normalmente USD). Antes el dashboard sumaba ``Factura.total``
sin mirar la moneda de cada factura -- una venta de Bs. 1.000 y otra de
$10 daban "1.010" -- y el frontend le pegaba un "$" fijo al resultado.

Criterio de conversión (contable, no "a la tasa de hoy"):

* En moneda base: cada factura aporta su ``total_base``, que ya se congeló
  con la tasa del día en que se emitió.
* En moneda de referencia: una factura emitida EN esa moneda aporta su
  ``total`` tal cual; una emitida en otra moneda aporta ``total_base``
  dividido entre la tasa de referencia vigente el día de la factura
  (historial de ``TasaCambio``). Así el total en $ de un mes pasado no
  cambia cada vez que se mueve la tasa.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Case, DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Value, When
from django.db.models.functions import Coalesce, NullIf

from apps.configuracion.models import Moneda, TasaCambio
from apps.configuracion.services.conversion_service import (
    MonedaNoEncontradaError,
    TasaNoDisponibleError,
    get_moneda_base,
    get_tasa_vigente,
)

MONEDA_BASE = "base"
MONEDA_REFERENCIA = "referencia"

_DECIMAL = DecimalField(max_digits=20, decimal_places=6)


@dataclass(frozen=True)
class MonedaReporte:
    """Moneda resuelta para un reporte."""

    moneda_id: int | None
    codigo: str
    simbolo: str
    es_base: bool
    #: Tasa vigente HOY de esta moneda frente a la base (1 si es la base).
    tasa_vigente: Decimal

    def as_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "simbolo": self.simbolo,
            "es_base": self.es_base,
            "tasa_vigente": str(self.tasa_vigente),
        }


def get_moneda_referencia() -> Moneda | None:
    """La moneda "dura" contra la que se compara la base: USD si está activa, si no la primera no-base activa."""
    no_base = Moneda.objects.filter(activa=True, es_predeterminada=False)
    return no_base.filter(codigo="USD").first() or no_base.order_by("codigo").first()


def _desde_moneda(moneda: Moneda, es_base: bool) -> MonedaReporte:
    return MonedaReporte(
        moneda_id=moneda.id,
        codigo=moneda.codigo,
        simbolo=moneda.simbolo or moneda.codigo,
        es_base=es_base,
        tasa_vigente=Decimal("1") if es_base else get_tasa_vigente(moneda.codigo),
    )


def resolver_moneda_reporte(valor: str | None) -> MonedaReporte:
    """
    Interpreta el query param ``?moneda=`` (``base`` | ``referencia`` | código ISO).

    Si se pide la referencia pero no hay moneda de referencia o no tiene tasa
    cargada, se cae a la base: mejor un reporte correcto en Bs. que uno
    "en dólares" con números inventados.
    """
    try:
        base = get_moneda_base()
    except MonedaNoEncontradaError:
        # Tenant sin monedas configuradas: todo está en una sola moneda
        # implícita y `total_base` == `total`.
        return MonedaReporte(moneda_id=None, codigo="", simbolo="", es_base=True, tasa_vigente=Decimal("1"))
    valor = (valor or MONEDA_BASE).strip()

    if valor == MONEDA_BASE or valor.upper() == base.codigo:
        return _desde_moneda(base, es_base=True)

    moneda = get_moneda_referencia() if valor == MONEDA_REFERENCIA else (
        Moneda.objects.filter(codigo=valor.upper(), activa=True).first()
    )
    if moneda is None:
        return _desde_moneda(base, es_base=True)
    try:
        return _desde_moneda(moneda, es_base=False)
    except (MonedaNoEncontradaError, TasaNoDisponibleError):
        return _desde_moneda(base, es_base=True)


def _tasa_historica(moneda: MonedaReporte, fecha_ref: str):
    """
    Tasa de ``moneda`` vigente en la fecha de ``fecha_ref`` (campo de fecha
    de la fila externa). Si no hay registro previo a esa fecha se usa el
    primero posterior, y en último caso la tasa de hoy.
    """
    tasas = TasaCambio.objects.filter(moneda_id=moneda.moneda_id, activa=True)
    previa = tasas.filter(fecha__lte=OuterRef(fecha_ref)).order_by("-fecha", "-id").values("tasa")[:1]
    posterior = tasas.filter(fecha__gt=OuterRef(fecha_ref)).order_by("fecha", "id").values("tasa")[:1]
    return NullIf(
        Coalesce(
            Subquery(previa, output_field=_DECIMAL),
            Subquery(posterior, output_field=_DECIMAL),
            Value(moneda.tasa_vigente, output_field=_DECIMAL),
        ),
        Value(Decimal("0"), output_field=_DECIMAL),
    )


def monto_documento(moneda: MonedaReporte, campo: str = "total", campo_base: str = "total_base", prefijo: str = ""):
    """
    Expresión (para ``annotate``/``aggregate``) del monto de un documento con
    moneda propia (Factura, Nota...) expresado en ``moneda``.

    ``prefijo`` permite usarla desde una relación (ej. ``"factura__"``).
    """
    base = F(f"{prefijo}{campo_base}")
    if moneda.es_base:
        return ExpressionWrapper(base, output_field=_DECIMAL)
    return Case(
        When(**{f"{prefijo}moneda_id": moneda.moneda_id}, then=F(f"{prefijo}{campo}")),
        default=ExpressionWrapper(base / _tasa_historica(moneda, f"{prefijo}fecha_operacion"), output_field=_DECIMAL),
        output_field=_DECIMAL,
    )


def monto_linea_factura(moneda: MonedaReporte):
    """Ingreso de una línea de factura (``cantidad * precio_unitario``) expresado en ``moneda``."""
    en_moneda_factura = F("cantidad") * F("precio_unitario")
    en_base = en_moneda_factura * Coalesce(F("factura__tasa_cambio"), Value(Decimal("1"), output_field=_DECIMAL))
    if moneda.es_base:
        return ExpressionWrapper(en_base, output_field=_DECIMAL)
    return Case(
        When(factura__moneda_id=moneda.moneda_id, then=en_moneda_factura),
        default=ExpressionWrapper(en_base / _tasa_historica(moneda, "factura__fecha_operacion"), output_field=_DECIMAL),
        output_field=_DECIMAL,
    )


def convertir_desde_base(monto_base: Decimal, moneda: MonedaReporte) -> Decimal:
    """Monto en moneda base -> ``moneda`` a la tasa vigente (valores "de hoy", ej. inventario)."""
    if moneda.es_base or not moneda.tasa_vigente:
        return Decimal(monto_base)
    return Decimal(monto_base) / moneda.tasa_vigente


def moneda_de_montos_comerciales() -> MonedaReporte:
    """
    Moneda en la que se expresan los montos comerciales que el usuario
    configura a mano (límite de crédito B2B, umbrales de nivel de precio):
    la de referencia si existe (así se mostraron siempre, con "$"), si no la
    base.
    """
    return resolver_moneda_reporte(MONEDA_REFERENCIA)
