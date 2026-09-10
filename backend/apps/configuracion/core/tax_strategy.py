"""
Motor de cálculo de impuestos basado en el **Patrón Strategy**.

Permite que el ERP soporte normativas fiscales de distintos países sin
acoplar la lógica de negocio a una jurisdicción concreta. Cada país
implementa una estrategia concreta; el registro `TaxStrategyRegistry`
resuelve la estrategia activa en función de la configuración global del
tenant.

Estrategias incluidas:
    * ``VenezuelaTaxStrategy`` — Providencias del SENIAT (IVA 16 % / 8 %,
      exento, retención ISLR 1 % / 2 %, notas de crédito/débito).
    * ``ColombiaTaxStrategy`` — Estructura preparada para la DIAN
      (IVA 19 %, 5 %, 0 %, retención en la fuente).
    * ``PeruTaxStrategy`` — Estructura preparada para la SUNAT
      (IGV 18 %, exonerado).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Type

# Constantes de redondeo
CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def _round_money(value: Decimal) -> Decimal:
    """Redondea un monto a 2 decimales con redondeo bancario (half-up)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class TaxStrategy(ABC):
    """
    Contrato que toda estrategia fiscal debe implementar.

    Los cálculos se realizan **sin IVA** (base imponible) y se devuelven los
    montos desglosados: subtotal, impuesto, retención y total.
    """

    country_code: str = "XX"
    country_name: str = "Generic"

    @abstractmethod
    def get_tax_rates(self) -> List[Dict[str, object]]:
        """Devuelve las tasas de impuesto aplicables (código, nombre, %)."""
        raise NotImplementedError

    @abstractmethod
    def calculate_tax(
        self,
        base: Decimal,
        tax_rate: Decimal,
        tax_type: str = "iva",
        exempt: bool = False,
    ) -> Decimal:
        """
        Calcula el monto de impuesto sobre una base imponible.

        Args:
            base: Base imponible (sin impuesto).
            tax_rate: Tasa porcentual (ej: 16 para 16 %).
            tax_type: Tipo de impuesto ('iva', 'igv', 'impoconsumo').
            exempt: Si es True, el bien está exento de impuesto.

        Returns:
            Decimal: Monto del impuesto.
        """
        raise NotImplementedError

    @abstractmethod
    def calculate_withholding(
        self,
        base: Decimal,
        withholding_rate: Decimal,
        withholding_type: str = "islr",
    ) -> Decimal:
        """
        Calcula la retención aplicable sobre la base.

        Usada para IVA retenido, ISLR, retención en la fuente, etc.
        """
        raise NotImplementedError


    def compute_totals(
        self,
        subtotal: Decimal,
        tax_breakdown: Dict[str, Decimal],
        discounts: Optional[Dict[str, Decimal]] = None,
        withholdings: Optional[Dict[str, Decimal]] = None,
        exempt_amount: Decimal = Decimal("0.00"),
    ) -> Dict[str, Decimal]:
        """
        Calcula los totales de una factura.

        Args:
            subtotal: Suma de las líneas (precio * cantidad) sin impuestos.
            tax_breakdown: Mapa {tipo_impuesto: monto_impuesto}.
            discounts: Mapa {tipo_descuento: monto}.
            withholdings: Mapa {tipo_retencion: monto}.
            exempt_amount: Monto exento (no genera impuesto).

        Returns:
            Dict con: subtotal, descuentos, base_imponible, impuestos,
            retenciones, exento, total.
        """
        discounts = discounts or {}
        withholdings = withholdings or {}

        total_discounts = sum(discounts.values(), Decimal("0.00"))
        base_imponible = subtotal - total_discounts
        total_taxes = sum(tax_breakdown.values(), Decimal("0.00"))
        total_withholdings = sum(withholdings.values(), Decimal("0.00"))

        total = _round_money(base_imponible + total_taxes - total_withholdings)

        return {
            "subtotal": _round_money(subtotal),
            "descuentos": _round_money(total_discounts),
            "base_imponible": _round_money(base_imponible),
            "impuestos": _round_money(total_taxes),
            "retenciones": _round_money(total_withholdings),
            "exento": _round_money(exempt_amount),
            "total": total,
        }


class VenezuelaTaxStrategy(TaxStrategy):
    """Implementación de las providencias fiscales del SENIAT (Venezuela)."""

    country_code = "VE"
    country_name = "Venezuela"

    # Tasas de IVA vigentes (Providencia administrativa)
    IVA_GENERAL = Decimal("16")
    IVA_REDUCIDO = Decimal("8")
    IVA_EXENTO = Decimal("0")

    # Retenciones aplicables
    RETENCION_ISLR_1 = Decimal("1")   # Agentes de retención (contribuyentes especiales)
    RETENCION_ISLR_2 = Decimal("2")   # Sujetos pasivos no calificados
    RETENCION_IVA_75 = Decimal("75")  # 75 % del IVA debito fiscal (casos especiales)

    def get_tax_rates(self) -> List[Dict[str, object]]:
        """Devuelve las tasas de IVA configuradas para Venezuela."""
        return [
            {"code": "IVA_GENERAL", "name": "IVA General", "rate": self.IVA_GENERAL},
            {"code": "IVA_REDUCIDO", "name": "IVA Reducido", "rate": self.IVA_REDUCIDO},
            {"code": "IVA_EXENTO", "name": "Exento", "rate": self.IVA_EXENTO},
        ]

    def calculate_tax(
        self,
        base: Decimal,
        tax_rate: Decimal,
        tax_type: str = "iva",
        exempt: bool = False,
    ) -> Decimal:
        """Calcula el IVA venezolano."""
        if exempt or tax_rate == Decimal("0"):
            return Decimal("0.00")
        return _round_money(base * tax_rate / HUNDRED)

    def calculate_withholding(
        self,
        base: Decimal,
        withholding_rate: Decimal,
        withholding_type: str = "islr",
    ) -> Decimal:
        """Calcula retenciones de ISLR / IVA conforme al SENIAT."""
        if withholding_type == "islr":
            return _round_money(base * withholding_rate / HUNDRED)
        if withholding_type == "iva":
            # Para IVA retenido se aplica la tasa de IVA sobre la base, escalada
            # por el factor de retención (ej: 75 % del IVA).
            return _round_money(base * withholding_rate / HUNDRED)
        return Decimal("0.00")


class ColombiaTaxStrategy(TaxStrategy):
    """Estructura preparada para la DIAN (Colombia)."""

    country_code = "CO"
    country_name = "Colombia"

    IVA_GENERAL = Decimal("19")
    IVA_REDUCIDO = Decimal("5")
    IVA_CERO = Decimal("0")
    RETENCION_FUENTE_2_5 = Decimal("2.5")

    def get_tax_rates(self) -> List[Dict[str, object]]:
        return [
            {"code": "IVA_GENERAL", "name": "IVA General", "rate": self.IVA_GENERAL},
            {"code": "IVA_REDUCIDO", "name": "IVA Reducido", "rate": self.IVA_REDUCIDO},
            {"code": "IVA_CERO", "name": "IVA 0 %", "rate": self.IVA_CERO},
        ]

    def calculate_tax(
        self,
        base: Decimal,
        tax_rate: Decimal,
        tax_type: str = "iva",
        exempt: bool = False,
    ) -> Decimal:
        if exempt or tax_rate == Decimal("0"):
            return Decimal("0.00")
        return _round_money(base * tax_rate / HUNDRED)

    def calculate_withholding(
        self,
        base: Decimal,
        withholding_rate: Decimal,
        withholding_type: str = "fuente",
    ) -> Decimal:
        return _round_money(base * withholding_rate / HUNDRED)


class PeruTaxStrategy(TaxStrategy):
    """Estructura preparada para la SUNAT (Perú)."""

    country_code = "PE"
    country_name = "Perú"

    IGV_GENERAL = Decimal("18")
    IGV_EXONERADO = Decimal("0")

    def get_tax_rates(self) -> List[Dict[str, object]]:
        return [
            {"code": "IGV_GENERAL", "name": "IGV General", "rate": self.IGV_GENERAL},
            {"code": "IGV_EXONERADO", "name": "Exonerado", "rate": self.IGV_EXONERADO},
        ]

    def calculate_tax(
        self,
        base: Decimal,
        tax_rate: Decimal,
        tax_type: str = "igv",
        exempt: bool = False,
    ) -> Decimal:
        if exempt or tax_rate == Decimal("0"):
            return Decimal("0.00")
        return _round_money(base * tax_rate / HUNDRED)

    def calculate_withholding(
        self,
        base: Decimal,
        withholding_rate: Decimal,
        withholding_type: str = "renta",
    ) -> Decimal:
        return _round_money(base * withholding_rate / HUNDRED)


class TaxStrategyRegistry:
    """
    Registro central de estrategias fiscales.

    Resuelve la estrategia correspondiente al país configurado en el tenant.
    """

    _strategies: Dict[str, Type[TaxStrategy]] = {
        "VE": VenezuelaTaxStrategy,
        "CO": ColombiaTaxStrategy,
        "PE": PeruTaxStrategy,
    }

    def __init__(self, country_code: str = "VE") -> None:
        self.country_code = country_code.upper()

    def get_strategy(self) -> TaxStrategy:
        """Devuelve una instancia de la estrategia activa."""
        strategy_class = self._strategies.get(self.country_code, VenezuelaTaxStrategy)
        return strategy_class()

    @classmethod
    def register(cls, code: str, strategy_class: Type[TaxStrategy]) -> None:
        """Permite registrar estrategias de nuevos países en runtime."""
        cls._strategies[code.upper()] = strategy_class

    @classmethod
    def available_countries(cls) -> List[Dict[str, str]]:
        """Lista de países soportados."""
        return [
            {
                "code": code,
                "country": strategy_class.country_name,
            }
            for code, strategy_class in cls._strategies.items()
        ]
