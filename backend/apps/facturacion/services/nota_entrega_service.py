"""
Notas de entrega: un documento que entrega mercancía de inmediato (descuenta
stock real, como una venta) pero SIN emitir todavía una factura fiscal --
para negocios que venden a crédito y no necesitan facturarle al cliente
hasta que confirme, o hasta cierta fecha. Reutiliza el modelo `Factura` en
vez de crear uno nuevo (mismas líneas, precios, cliente) con
`estado='nota_entrega'`: mientras esté en ese estado, `Factura.save()` nunca
le asigna correlativo/número de control (ver esa lógica), así que no "quema"
numeración fiscal hasta que de verdad se convierte en factura.
"""
from django.db import transaction

from ..models import Factura
from .pagos_service import afectar_inventario_por_venta


class NotaEntregaError(Exception):
    pass


@transaction.atomic
def confirmar_nota_entrega(factura: Factura) -> Factura:
    """
    Descuenta el stock de una nota de entrega recién creada. A diferencia de
    una factura normal (que descuenta al COBRARSE, ver
    `afectar_inventario_por_venta`), una nota de entrega entrega la
    mercancía de inmediato, antes de facturar o cobrar -- su stock sale en
    el momento de confirmarse, no cuando alguien pague después.
    """
    if factura.estado != 'nota_entrega':
        raise NotaEntregaError("Esta operación solo aplica a notas de entrega.")
    afectar_inventario_por_venta(factura)
    return factura


@transaction.atomic
def convertir_nota_entrega_a_factura(factura: Factura, condicion_pago: str = 'contado') -> Factura:
    """
    Convierte una nota de entrega en una factura fiscal real: al pasar a
    `estado='pendiente'`, `Factura.save()` recién ahí le asigna correlativo
    y número de control SENIAT. Nunca vuelve a tocar el stock -- ya salió al
    confirmarse la nota de entrega (`inventario_afectado` sigue en `True`,
    así que `afectar_inventario_por_venta` no hace nada si luego se le
    registra un pago).
    """
    if factura.estado != 'nota_entrega':
        raise NotaEntregaError("Esta factura no es una nota de entrega.")
    if not factura.inventario_afectado:
        raise NotaEntregaError("Esta nota de entrega todavía no descontó su stock -- no se puede facturar así.")
    factura.estado = 'pendiente'
    factura.condicion_pago = condicion_pago
    # El correlativo que tenía era el de Nota de Entrega (no fiscal, ver
    # `ConfiguracionCorrelativo.prefijo_nota_entrega`) -- se limpia para que
    # `Factura.save()` le asigne uno real de la secuencia fiscal de
    # facturas, igual que si se estuviera facturando por primera vez.
    factura.correlativo = None
    factura.save()
    return factura
