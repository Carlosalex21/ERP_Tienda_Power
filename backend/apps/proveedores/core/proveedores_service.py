# apps/proveedores/core/proveedores_service.py
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.proveedores.models import CuentaPorPagar, PagoProveedor, Proveedor

CENT = Decimal('0.01')


def desactivar_proveedor_service(proveedor_id):
    """
    Lógica de negocio para "eliminar" (desactivar) un proveedor.
    """
    try:
        proveedor = Proveedor.objects.get(id=proveedor_id, activo=True)

        # --- LÓGICA DE NEGOCIO FUTURA AQUÍ ---
        # Ejemplo: Verificar si hay pedidos pendientes antes de desactivar
        # pedidos_pendientes = Pedidoproveedor.objects.filter(proveedor=proveedor, estado='pendiente').exists()
        # if pedidos_pendientes:
        #     raise ValueError("No se puede desactivar un proveedor con pedidos pendientes.")

        proveedor.activo = False
        proveedor.save(update_fields=['activo'])
        return proveedor

    except Proveedor.DoesNotExist:
        raise ValueError("El proveedor no existe o ya está inactivo.")

def verificar_limite_credito(proveedor_id, monto_nuevo_pedido):
    """
    Ejemplo de un servicio adicional útil para el futuro.
    """
    pass


def _round(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


class CuentaPorPagarError(Exception):
    """Error controlado al crear/pagar una cuenta por pagar."""


def crear_cuenta_por_pagar_desde_ajuste(ajuste) -> CuentaPorPagar | None:
    """
    Se llama DESPUÉS de que un `AjusteInventario` de entrada ya se aplicó
    sobre el stock real (ver `stock_service.crear_y_aplicar_ajuste`) --
    mismo criterio defensivo que los asientos automáticos de contabilidad:
    nunca debe poder tumbar el ajuste ya aplicado.

    Solo crea la cuenta si el ajuste es una COMPRA (con o sin factura
    fiscal), tiene un proveedor asociado, y al menos una línea trae
    `costo_unitario` (sin costo no hay monto que cobrar/deber). Si ya existe
    una cuenta para este ajuste (reintento), no duplica.
    """
    try:
        if ajuste.tipo != 'entrada' or ajuste.motivo not in ('compra_con_factura', 'compra_sin_factura'):
            return None
        if not ajuste.proveedor_id:
            return None
        if CuentaPorPagar.objects.filter(ajuste_origen=ajuste).exists():
            return None

        monto = Decimal('0.00')
        for detalle in ajuste.detalles.all():
            if detalle.costo_unitario:
                monto += Decimal(detalle.cantidad) * Decimal(detalle.costo_unitario)
        monto = _round(monto)
        if monto <= 0:
            return None

        fecha_emision = ajuste.fecha_efectiva
        fecha_vencimiento = None
        if ajuste.proveedor.plazo_pago:
            fecha_vencimiento = fecha_emision + timedelta(days=ajuste.proveedor.plazo_pago)

        return CuentaPorPagar.objects.create(
            proveedor=ajuste.proveedor,
            numero_documento=ajuste.numero_documento or '',
            fecha_emision=fecha_emision,
            fecha_vencimiento=fecha_vencimiento,
            monto=monto,
            ajuste_origen=ajuste,
            usuario=ajuste.usuario,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning('No se pudo crear la cuenta por pagar del ajuste %s', getattr(ajuste, 'id', '?'), exc_info=True)
        return None


def sincronizar_cuenta_por_pagar_desde_ajuste(ajuste) -> None:
    """
    Si el `ajuste` ya generó una `CuentaPorPagar` (ver
    `crear_cuenta_por_pagar_desde_ajuste`) y luego se corrige su fecha de
    documento o su proveedor, la cuenta ya creada queda con datos viejos --
    esto la pone al día. Se llama desde
    `AjusteInventarioViewSet.partial_update` cada vez que se edita un ajuste
    con cuenta asociada. No hace nada si la cuenta ya se pagó/anuló: alterar
    el vencimiento de algo que ya se saldó no tiene efecto útil y podría
    confundir el historial.
    """
    cuenta = CuentaPorPagar.objects.filter(ajuste_origen=ajuste, estado='pendiente').first()
    if cuenta is None:
        return
    cuenta.fecha_emision = ajuste.fecha_efectiva
    cuenta.fecha_vencimiento = (
        ajuste.fecha_efectiva + timedelta(days=ajuste.proveedor.plazo_pago)
        if ajuste.proveedor_id and ajuste.proveedor.plazo_pago
        else None
    )
    cuenta.numero_documento = ajuste.numero_documento or cuenta.numero_documento
    cuenta.save(update_fields=['fecha_emision', 'fecha_vencimiento', 'numero_documento'])


@transaction.atomic
def registrar_pago_proveedor(*, cuenta_id, monto, usuario, metodo_pago_id=None, referencia=''):
    """
    Registra un abono/pago contra una `CuentaPorPagar` -- puede ser parcial
    (varios pagos hasta saldarla). Genera, además, el asiento contable
    automático (Debe Cuentas por Pagar / Haber Caja) -- ver
    `apps.contabilidad.services.generar_asiento_automatico_pago_proveedor`.
    """
    cuenta = CuentaPorPagar.objects.select_for_update().filter(pk=cuenta_id).first()
    if cuenta is None:
        raise CuentaPorPagarError('Cuenta por pagar no encontrada.')
    if cuenta.estado != 'pendiente':
        raise CuentaPorPagarError('Esta cuenta ya no está pendiente (pagada o anulada).')

    monto = _round(monto)
    saldo = cuenta.saldo_pendiente
    if monto <= 0:
        raise CuentaPorPagarError('El monto del pago debe ser mayor a cero.')
    if monto > saldo:
        raise CuentaPorPagarError(f'El pago ({monto}) no puede superar el saldo pendiente ({saldo}).')

    pago = PagoProveedor.objects.create(
        cuenta_por_pagar=cuenta, monto=monto, metodo_pago_id=metodo_pago_id,
        referencia=referencia, usuario=usuario,
    )
    cuenta.monto_pagado = cuenta.monto_pagado + monto
    if cuenta.monto_pagado >= cuenta.monto:
        cuenta.estado = 'pagada'
    cuenta.save(update_fields=['monto_pagado', 'estado'])

    try:
        from apps.contabilidad.services import generar_asiento_automatico_pago_proveedor
        generar_asiento_automatico_pago_proveedor(pago)
    except Exception:
        pass

    return pago


def reporte_cuentas_por_pagar(fecha_corte=None) -> list[dict]:
    """
    Agrupa por proveedor las cuentas pendientes, con antigüedad de saldos
    (0-30/31-60/61-90/90+ días desde `fecha_emision` hasta `fecha_corte`) --
    el mismo criterio que `apps.facturacion.services.pagos_service.reporte_cuentas_por_cobrar`,
    reflejado del otro lado del balance.
    """
    fecha_corte = fecha_corte or timezone.localdate()
    cuentas = CuentaPorPagar.objects.filter(estado='pendiente').select_related('proveedor')

    por_proveedor: dict[int, dict] = {}
    for cuenta in cuentas:
        saldo = cuenta.saldo_pendiente
        if saldo <= 0:
            continue
        dias = (fecha_corte - cuenta.fecha_emision).days
        bucket = '0_30' if dias <= 30 else '31_60' if dias <= 60 else '61_90' if dias <= 90 else 'mas_90'

        entry = por_proveedor.setdefault(cuenta.proveedor_id, {
            'proveedor_id': cuenta.proveedor_id,
            'proveedor_nombre': cuenta.proveedor.nombre,
            'total': Decimal('0.00'),
            '0_30': Decimal('0.00'),
            '31_60': Decimal('0.00'),
            '61_90': Decimal('0.00'),
            'mas_90': Decimal('0.00'),
            'cuentas': [],
        })
        entry['total'] += saldo
        entry[bucket] += saldo
        entry['cuentas'].append({
            'id': cuenta.id,
            'numero_documento': cuenta.numero_documento,
            'fecha_emision': cuenta.fecha_emision.isoformat(),
            'fecha_vencimiento': cuenta.fecha_vencimiento.isoformat() if cuenta.fecha_vencimiento else None,
            'monto': str(_round(cuenta.monto)),
            'saldo_pendiente': str(_round(saldo)),
            'dias': dias,
        })

    filas = list(por_proveedor.values())
    for fila in filas:
        for campo in ('total', '0_30', '31_60', '61_90', 'mas_90'):
            fila[campo] = str(_round(fila[campo]))
    filas.sort(key=lambda f: Decimal(f['total']), reverse=True)
    return filas
