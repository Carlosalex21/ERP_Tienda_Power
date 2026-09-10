"""
Servicio de registro automático de los Libros de Compra y Venta (SENIAT).

Cada factura, nota de crédito o nota de débito genera una línea en el libro
de ventas (o de compras), de forma que el contribuyente pueda declarar su
débito/crédito fiscal sin intervención manual.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from apps.facturacion.models import LibroCompraVenta




def registrar_en_libro_compra_venta(
    *,
    tipo_libro: str,
    fecha_operacion,
    tipo_documento: str,
    numero_documento: str,
    numero_control: Optional[str] = None,
    rif: Optional[str] = None,
    razon_social: str,
    base_imponible: Decimal = Decimal("0.00"),
    iva: Decimal = Decimal("0.00"),
    retencion: Decimal = Decimal("0.00"),
    total: Decimal = Decimal("0.00"),
) -> LibroCompraVenta:
    """
    Registra una línea en el Libro de Compra o de Venta.

    Args:
        tipo_libro: 'compra' o 'venta'.
        fecha_operacion: Fecha de la operación (date/datetime).
        tipo_documento: 'Factura', 'Nota de Crédito', 'Nota de Débito'.
        numero_documento: Correlativo / número de la factura o nota.
        numero_control: Número de control SENIAT.
        rif: RIF del contribuyente involucrado.
        razon_social: Razón social o nombre del contribuyente.
        base_imponible: Base imponible de la línea.
        iva: Monto de IVA.
        retencion: Monto de retención.
        total: Monto total.

    Returns:
        LibroCompraVenta: La línea creada.
    """
    return LibroCompraVenta.objects.create(
        tipo_libro=tipo_libro,
        fecha_operacion=fecha_operacion,
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
        numero_control=numero_control,
        rif=rif,
        razon_social=razon_social,
        base_imponible=Decimal(base_imponible or 0),
        iva=Decimal(iva or 0),
        retencion=Decimal(retencion or 0),
        total=Decimal(total or 0),
    )


def registrar_factura_en_libro(factura) -> LibroCompraVenta:
    """
    Registra una factura en el libro de ventas.

    Si la factura tiene cliente, usa sus datos (RIF, razón social). En caso
    contrario, usa la configuración de la empresa (operación a consumidor
    final, sin RIF).

    Args:
        factura: Instancia de ``Factura``.

    Returns:
        LibroCompraVenta: La línea registrada.
    """
    from apps.configuracion.models import ConfiguracionEmpresa

    razon_social = None
    rif = None
    if factura.cliente is not None:
        razon_social = factura.cliente.nombre
        rif = factura.cliente.documento
    if not razon_social:
        empresa = ConfiguracionEmpresa.objects.filter(pk=1).first()
        razon_social = (
            empresa.nombre_comercial if empresa else "Consumidor Final"
        )
        rif = empresa.rif if empresa else None

    return registrar_en_libro_compra_venta(


        tipo_libro="venta",
        fecha_operacion=factura.fecha_operacion.date(),
        tipo_documento="Factura",
        numero_documento=factura.correlativo or "",
        numero_control=factura.numero_control,
        rif=rif,
        razon_social=razon_social or "Consumidor Final",
        base_imponible=factura.base_imponible,
        iva=factura.iva_total,
        retencion=factura.retencion_total,
        total=factura.total,
    )
