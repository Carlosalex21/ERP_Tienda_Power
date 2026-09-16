"""
Adaptadores de facturación electrónica -- Patrón Strategy/Adapter.

Espejo de ``apps.configuracion.core.tax_strategy``: cada país con requisitos
de facturación electrónica implementa un ``InvoicingAdapter`` concreto y se
registra en ``InvoicingAdapterRegistry``. El motor de facturación no conoce
los detalles de ningún proveedor fiscal específico (SENIAT/DIAN/SUNAT); solo
llama a ``adapter.emitir(factura)`` y persiste el ``Facturaelectronica`` que
el resultado describe (ver ``apps.facturacion.services.facturaelectronica_service``).

Ningún adapter concreto implementa hoy una integración real contra un
servicio de gobierno -- eso requiere credenciales/certificados por tenant
que este ERP todavía no gestiona. Lo que este módulo resuelve es la
arquitectura: un único punto de extensión para cuando esa integración se
implemente, sin acoplar el core de facturación a un país.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional, Type


class InvoicingResult:
    """Resultado de intentar emitir una factura electrónica ante un proveedor fiscal."""

    def __init__(
        self,
        estado: str,
        csv: Optional[str] = None,
        qr_code: Optional[bytes] = None,
        firma_electronica: Optional[str] = None,
        respuesta_proveedor: Optional[dict] = None,
    ) -> None:
        self.estado = estado
        self.csv = csv
        self.qr_code = qr_code
        self.firma_electronica = firma_electronica
        self.respuesta_proveedor = respuesta_proveedor or {}


class InvoicingAdapter(ABC):
    """Contrato que todo adapter de facturación electrónica debe implementar."""

    country_code: str = "XX"
    provider_name: str = "generic"

    @abstractmethod
    def emitir(self, factura) -> InvoicingResult:
        """
        Envía la factura al proveedor fiscal del país y devuelve el resultado.

        Args:
            factura: Instancia de ``apps.facturacion.models.Factura``.
        """
        raise NotImplementedError


class SeniatAdapter(InvoicingAdapter):
    """
    Adapter para facturación electrónica ante el SENIAT (Venezuela).

    **Estado: no implementado.** Requiere integrar un proveedor autorizado
    de facturación electrónica (o el servicio del SENIAT, según el régimen
    del tenant) con las credenciales/certificado correspondientes. Devuelve
    explícitamente ``estado='no_soportado'`` en vez de fingir un envío
    exitoso -- ver ``apps.facturacion.models.Facturaelectronica.ESTADO_CHOICES``.
    """

    country_code = "VE"
    provider_name = "seniat"

    def emitir(self, factura) -> InvoicingResult:
        return InvoicingResult(
            estado="no_soportado",
            respuesta_proveedor={
                "detalle": (
                    "Integración con proveedor de facturación electrónica "
                    "SENIAT pendiente de implementar."
                ),
            },
        )


class InvoicingAdapterRegistry:
    """Registro central de adapters de facturación electrónica por país."""

    _adapters: Dict[str, Type[InvoicingAdapter]] = {
        "VE": SeniatAdapter,
    }

    def __init__(self, country_code: str) -> None:
        self.country_code = country_code.upper()

    def get_adapter(self) -> Optional[InvoicingAdapter]:
        """Devuelve el adapter del país activo, o ``None`` si no hay ninguno registrado."""
        adapter_class = self._adapters.get(self.country_code)
        return adapter_class() if adapter_class else None

    @classmethod
    def register(cls, code: str, adapter_class: Type[InvoicingAdapter]) -> None:
        """Permite registrar adapters de nuevos países en runtime (ej. DianAdapter, SunatAdapter)."""
        cls._adapters[code.upper()] = adapter_class
