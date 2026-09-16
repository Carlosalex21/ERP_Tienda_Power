"""
Servicio de facturación electrónica.

Resuelve el ``InvoicingAdapter`` del país del tenant (mismo patrón de
resolución que ``calculos_service._resolve_strategy``) y persiste el
resultado en ``Facturaelectronica``.

No se invoca automáticamente desde ``FacturaViewSet``/señales todavía: hoy
todo país resuelve a ``estado='no_soportado'`` (ver ``SeniatAdapter``), así
que llamarlo en cada emisión solo generaría ruido. Queda disponible para
conectarse cuando exista un adapter real.
"""
from __future__ import annotations

from django.utils import timezone

from apps.configuracion.core.config_service import obtener_pais_tenant
from apps.facturacion.core.invoicing_adapter import InvoicingAdapterRegistry
from apps.facturacion.models import Factura, Facturaelectronica


def emitir_factura_electronica(factura: Factura) -> Facturaelectronica:
    """
    Emite (o intenta emitir) la factura electrónica ante el proveedor fiscal
    del país del tenant, y persiste el resultado en ``Facturaelectronica``.

    Args:
        factura: Instancia de ``Factura`` ya guardada.

    Returns:
        Facturaelectronica: el registro creado o actualizado.
    """
    country_code = obtener_pais_tenant()
    adapter = InvoicingAdapterRegistry(country_code).get_adapter()

    if adapter is None:
        registro, _ = Facturaelectronica.objects.update_or_create(
            factura=factura,
            defaults={
                "estado": "no_soportado",
                "respuesta_proveedor": {
                    "detalle": f"Sin proveedor de facturación electrónica registrado para '{country_code}'.",
                },
                "fecha_procesado": timezone.now(),
            },
        )
        return registro

    resultado = adapter.emitir(factura)
    registro, _ = Facturaelectronica.objects.update_or_create(
        factura=factura,
        defaults={
            "proveedor_codigo": adapter.provider_name,
            "estado": resultado.estado,
            "csv": resultado.csv,
            "qr_code": resultado.qr_code,
            "firma_electronica": resultado.firma_electronica,
            "respuesta_proveedor": resultado.respuesta_proveedor,
            "fecha_procesado": timezone.now(),
        },
    )
    return registro
