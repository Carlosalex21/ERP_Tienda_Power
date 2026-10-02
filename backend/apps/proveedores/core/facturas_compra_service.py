# apps/proveedores/core/facturas_compra_service.py
"""
Registro de compras a proveedores (`FacturaCompra`).

Una factura de compra hace, en una sola transacción, todo lo que una compra
real implica:

1. Entrada de inventario de sus líneas (costo SIN IVA -> costo promedio).
2. Si viene de una orden de compra, suma lo recibido a esa orden.
3. Cuenta por pagar al proveedor por el total.
4. Línea en el Libro de Compras (solo factura fiscal, no nota de entrega).
5. Asiento contable: Inventario + IVA crédito fiscal contra Cuentas por Pagar.
6. Comprobante de retención de IVA, si el negocio es agente de retención y
   se indicó el porcentaje (75% / 100%).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.proveedores.models import CuentaPorPagar, FacturaCompra, FacturaCompraDetalle, OrdenCompra, Proveedor

CENT = Decimal('0.01')
HUNDRED = Decimal('100')


class FacturaCompraError(Exception):
    """Error controlado al registrar/anular una factura de compra."""


def _round(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def calcular_montos(*, detalles, monto_exento, base_imponible, porcentaje_iva) -> dict:
    """
    Montos de la factura. Con líneas de producto, el subtotal sale de ellas
    (cantidad x costo sin IVA) y la parte exenta se descuenta de ese
    subtotal para obtener la base gravada; sin líneas (un gasto), la base y
    el exento se indican a mano.
    """
    exento = _round(monto_exento)
    if exento < 0:
        raise FacturaCompraError('El monto exento no puede ser negativo.')
    porcentaje_iva = Decimal(porcentaje_iva or 0)
    if porcentaje_iva < 0:
        raise FacturaCompraError('El porcentaje de IVA no puede ser negativo.')

    if detalles:
        subtotal = _round(sum(Decimal(d['cantidad']) * Decimal(d['costo_unitario']) for d in detalles))
        if exento > subtotal:
            raise FacturaCompraError('El monto exento no puede superar el subtotal de los productos.')
        base = subtotal - exento
    else:
        base = _round(base_imponible)
        if base < 0:
            raise FacturaCompraError('La base imponible no puede ser negativa.')

    iva = _round(base * porcentaje_iva / HUNDRED)
    total = base + exento + iva
    if total <= 0:
        raise FacturaCompraError('El total de la factura debe ser mayor a cero.')
    return {'monto_exento': exento, 'base_imponible': base, 'iva': iva, 'total': total}


@transaction.atomic
def registrar_factura_compra(
    *,
    usuario,
    proveedor: Proveedor,
    tipo_documento: str,
    numero_factura: str,
    numero_control: str = '',
    fecha_emision,
    almacen=None,
    orden_compra: OrdenCompra | None = None,
    detalles: list[dict],
    monto_exento=0,
    base_imponible=0,
    porcentaje_iva=0,
    porcentaje_retencion_iva=0,
    observaciones: str = '',
) -> FacturaCompra:
    """
    `detalles`: lista de `{producto, variante, cantidad, costo_unitario,
    orden_detalle_id}` (instancias ya validadas por el serializer).
    """
    from apps.inventario.services.stock_service import crear_y_aplicar_ajuste
    from apps.proveedores.core.compras_service import OrdenCompraError, recibir_lineas_orden_compra

    numero_factura = (numero_factura or '').strip()
    numero_control = (numero_control or '').strip()
    es_factura = tipo_documento == 'factura'

    if not numero_factura:
        raise FacturaCompraError('Indica el número del documento del proveedor.')
    if es_factura and not numero_control:
        raise FacturaCompraError('Una factura fiscal debe traer su número de control (está impreso en la factura).')
    if fecha_emision > timezone.localdate():
        raise FacturaCompraError('La fecha de emisión no puede ser futura.')
    if not es_factura:
        # Una nota de entrega no es un documento fiscal: no discrimina IVA,
        # no va al Libro de Compras y no admite retención.
        numero_control = ''
        porcentaje_iva = 0
        porcentaje_retencion_iva = 0
    if Decimal(porcentaje_retencion_iva or 0) not in (Decimal('0'), Decimal('75'), Decimal('100')):
        raise FacturaCompraError('La retención de IVA solo puede ser 75% o 100% (o ninguna).')

    if FacturaCompra.objects.filter(
        proveedor=proveedor, tipo_documento=tipo_documento, numero_factura=numero_factura, estado='registrada',
    ).exists():
        raise FacturaCompraError(f'Ya registraste el documento {numero_factura} de {proveedor.nombre}.')

    for d in detalles:
        if d['cantidad'] <= 0:
            raise FacturaCompraError('La cantidad de cada línea debe ser mayor a cero.')
        if not d.get('costo_unitario') or Decimal(d['costo_unitario']) <= 0:
            raise FacturaCompraError(f'Indica el costo unitario (sin IVA) de "{d["producto"].nombre}".')
    if detalles and almacen is None:
        raise FacturaCompraError('Indica en qué almacén entra la mercancía.')

    montos = calcular_montos(
        detalles=detalles, monto_exento=monto_exento, base_imponible=base_imponible, porcentaje_iva=porcentaje_iva,
    )

    if orden_compra is not None:
        if orden_compra.proveedor_id != proveedor.pk:
            raise FacturaCompraError('La orden de compra es de otro proveedor.')
        lineas_oc = [(d['orden_detalle_id'], d['cantidad']) for d in detalles if d.get('orden_detalle_id')]
        if not lineas_oc:
            raise FacturaCompraError('Indica qué productos de la orden de compra llegaron con esta factura.')
        try:
            recibir_lineas_orden_compra(orden_compra, lineas_oc)
        except OrdenCompraError as exc:
            raise FacturaCompraError(str(exc)) from exc

    factura = FacturaCompra.objects.create(
        proveedor=proveedor,
        tipo_documento=tipo_documento,
        numero_factura=numero_factura,
        numero_control=numero_control,
        fecha_emision=fecha_emision,
        orden_compra=orden_compra,
        almacen=almacen,
        porcentaje_iva=Decimal(porcentaje_iva or 0),
        observaciones=observaciones or '',
        usuario=usuario,
        **montos,
    )
    for d in detalles:
        FacturaCompraDetalle.objects.create(
            factura=factura,
            producto=d['producto'],
            variante=d.get('variante'),
            orden_detalle_id=d.get('orden_detalle_id'),
            cantidad=d['cantidad'],
            costo_unitario=d['costo_unitario'],
        )

    # 1. Inventario
    if detalles:
        try:
            factura.ajuste = crear_y_aplicar_ajuste(
                usuario=usuario,
                generar_asiento=False,
                detalles_data=[
                    {
                        'producto': d['producto'], 'variante': d.get('variante'),
                        'cantidad': d['cantidad'], 'costo_unitario': d['costo_unitario'],
                    }
                    for d in detalles
                ],
                tipo='entrada',
                motivo='compra_con_factura' if es_factura else 'compra_sin_factura',
                proveedor=proveedor,
                almacen=almacen,
                numero_documento=numero_factura,
                numero_control=numero_control,
                fecha_documento=fecha_emision,
                observaciones=f'Entrada por {factura}',
            )
        except ValueError as exc:
            raise FacturaCompraError(str(exc)) from exc

    # 2. Cuenta por pagar (por el total; cada retención la rebaja después)
    CuentaPorPagar.objects.create(
        proveedor=proveedor,
        numero_documento=numero_factura,
        fecha_emision=fecha_emision,
        fecha_vencimiento=(fecha_emision + timedelta(days=proveedor.plazo_pago)) if proveedor.plazo_pago else None,
        monto=factura.total,
        factura_compra=factura,
        usuario=usuario,
    )

    # 3. Asiento contable (aislado: nunca tumba la compra)
    from apps.contabilidad.services import generar_asiento_automatico_factura_compra
    factura.asiento = generar_asiento_automatico_factura_compra(factura)
    factura.save(update_fields=['ajuste', 'asiento'])

    # 4. Libro de Compras
    sincronizar_libro_compras(factura)

    # 5. Retención de IVA
    if es_factura and Decimal(porcentaje_retencion_iva or 0) > 0 and factura.iva > 0:
        from apps.facturacion.services.retencion_service import crear_comprobante_retencion
        crear_comprobante_retencion(
            factura_compra=factura,
            tipo_retencion='iva',
            porcentaje=Decimal(porcentaje_retencion_iva),
            base=factura.iva,
        )
        factura.refresh_from_db()

    return factura


def sincronizar_libro_compras(factura: FacturaCompra) -> None:
    """Crea/actualiza (o da de baja, si se anuló) la línea de la factura en el Libro de Compras."""
    from apps.facturacion.models import LibroCompraVenta

    if factura.tipo_documento != 'factura':
        return
    if factura.estado == 'anulada':
        LibroCompraVenta.objects.filter(factura_compra=factura).update(activo=False)
        return
    LibroCompraVenta.objects.update_or_create(
        factura_compra=factura,
        defaults=dict(
            tipo_libro='compra',
            fecha_operacion=factura.fecha_emision,
            tipo_documento='Factura',
            numero_documento=factura.numero_factura,
            numero_control=factura.numero_control or None,
            rif=factura.proveedor.identificador_fiscal,
            razon_social=factura.proveedor.nombre,
            base_imponible=factura.base_imponible,
            iva=factura.iva,
            retencion=factura.retencion_iva,
            total=factura.total,
            activo=True,
        ),
    )


@transaction.atomic
def recalcular_retenciones_factura(factura: FacturaCompra) -> FacturaCompra:
    """
    Se llama cada vez que se emite, edita o anula una retención sobre esta
    factura: actualiza los totales retenidos, el saldo de la cuenta por
    pagar (lo retenido se le paga al fisco, no al proveedor) y la columna
    de retención del Libro de Compras.
    """
    from django.db.models import Sum

    factura = FacturaCompra.objects.select_for_update().get(pk=factura.pk)
    activas = factura.retenciones.filter(activo=True)
    factura.retencion_iva = _round(activas.filter(tipo_retencion='iva').aggregate(s=Sum('monto'))['s'])
    factura.retencion_islr = _round(activas.exclude(tipo_retencion='iva').aggregate(s=Sum('monto'))['s'])
    if factura.retencion_iva + factura.retencion_islr > factura.total:
        raise FacturaCompraError('Las retenciones no pueden superar el total de la factura.')
    factura.save(update_fields=['retencion_iva', 'retencion_islr'])

    cuenta = factura.cuentas_por_pagar.exclude(estado='anulada').first()
    if cuenta is not None:
        nuevo_monto = factura.total - factura.retencion_iva - factura.retencion_islr
        if nuevo_monto < cuenta.monto_pagado:
            raise FacturaCompraError(
                f'Ya se le pagaron {cuenta.monto_pagado} al proveedor; con esta retención la deuda quedaría en {nuevo_monto}.'
            )
        cuenta.monto = nuevo_monto
        cuenta.estado = 'pagada' if cuenta.monto_pagado >= nuevo_monto else 'pendiente'
        cuenta.save(update_fields=['monto', 'estado'])

    sincronizar_libro_compras(factura)
    return factura


@transaction.atomic
def anular_factura_compra(factura: FacturaCompra, *, usuario) -> FacturaCompra:
    """
    Anula una compra cargada por error: saca del inventario lo que había
    entrado, devuelve lo recibido a la orden de compra, anula la cuenta por
    pagar, sus retenciones, su asiento y su línea del Libro de Compras.
    Solo si todavía no se le pagó nada al proveedor -- con pagos, lo que
    corresponde es una nota de crédito/devolución, no borrar la compra.
    """
    from apps.contabilidad.services import anular_asiento_si_existe
    from apps.inventario.services.stock_service import crear_y_aplicar_ajuste
    from apps.proveedores.core.compras_service import revertir_lineas_orden_compra

    factura = FacturaCompra.objects.select_for_update().get(pk=factura.pk)
    if factura.estado == 'anulada':
        raise FacturaCompraError('Esta factura ya está anulada.')
    cuentas = list(factura.cuentas_por_pagar.select_for_update())
    if any(c.monto_pagado > 0 for c in cuentas):
        raise FacturaCompraError('Esta compra ya tiene pagos registrados al proveedor -- no se puede anular.')

    detalles = list(factura.detalles.select_related('producto', 'variante'))
    if detalles:
        try:
            crear_y_aplicar_ajuste(
                usuario=usuario,
                generar_asiento=False,
                detalles_data=[
                    {'producto': d.producto, 'variante': d.variante, 'cantidad': d.cantidad, 'costo_unitario': d.costo_unitario}
                    for d in detalles
                ],
                tipo='salida',
                motivo='devolucion_proveedor',
                proveedor=factura.proveedor,
                almacen=factura.almacen,
                numero_documento=factura.numero_factura,
                observaciones=f'Anulación de {factura}',
            )
        except ValueError as exc:
            raise FacturaCompraError(
                f'No se puede anular: parte de esa mercancía ya se vendió o movió ({exc}).'
            ) from exc

    if factura.orden_compra_id:
        revertir_lineas_orden_compra(
            factura.orden_compra, [(d.orden_detalle_id, d.cantidad) for d in detalles if d.orden_detalle_id],
        )

    for cuenta in cuentas:
        cuenta.estado = 'anulada'
        cuenta.save(update_fields=['estado'])

    for retencion in factura.retenciones.filter(activo=True):
        retencion.activo = False
        retencion.save(update_fields=['activo'])
        anular_asiento_si_existe(retencion.asiento)

    anular_asiento_si_existe(factura.asiento)

    factura.estado = 'anulada'
    factura.fecha_anulacion = timezone.now()
    factura.save(update_fields=['estado', 'fecha_anulacion'])
    sincronizar_libro_compras(factura)
    return factura
