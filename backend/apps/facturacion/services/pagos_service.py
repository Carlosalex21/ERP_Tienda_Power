import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.facturacion.models import CajaSesion, Detallefactura, Factura, MetodoPago, Transaccionpago
from apps.inventario.services.stock_service import reducir_stock_item

CENT = Decimal("0.01")


class PagoServiceError(Exception):
    """Error controlado al registrar pagos (usado además de ValueError por compatibilidad con las vistas)."""


def afectar_inventario_por_venta(factura):
    """
    Recorre los detalles de la factura y delega la reducción de stock
    al servicio especializado del módulo de inventario.

    Idempotente vía `factura.inventario_afectado`: una nota de entrega
    (`estado='nota_entrega'`) ya descontó su stock al crearse (ver
    `NotaEntregaService`/`crear_nota_entrega`), así que cuando luego se
    convierte en factura y se le registra un pago normal, esta función NO
    debe volver a descontar lo mismo.
    """
    if factura.inventario_afectado:
        return
    detalles = Detallefactura.objects.select_related('producto', 'variante', 'presentacion').filter(factura=factura)
    for detalle in detalles:
        # Un producto tipo='servicio' (ej. "Servicio Técnico") no tiene stock
        # que descontar -- venderlo no debe fallar con "stock insuficiente"
        # solo porque nunca tuvo cantidad cargada.
        if detalle.variante is None and detalle.producto is not None and detalle.producto.tipo == 'servicio':
            continue
        # Determinamos si vendimos una variante específica o el producto base
        item_vendido = detalle.variante if detalle.variante else detalle.producto
        # `detalle.cantidad` está en unidades de la PRESENTACIÓN vendida (ej.
        # "2" significa 2 bultos, no 2 unidades) -- hay que multiplicar por su
        # factor de conversión para descontar las unidades base reales.
        # Las presentaciones solo aplican a productos simples (ver
        # `PresentacionProducto`), así que nunca coexisten con `variante`.
        cantidad_base = detalle.cantidad
        if detalle.presentacion is not None:
            cantidad_base = detalle.cantidad * detalle.presentacion.factor_conversion
        reducir_stock_item(item_vendido, cantidad_base)
    factura.inventario_afectado = True
    factura.save(update_fields=['inventario_afectado'])


def _round(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


@transaction.atomic
def procesar_pago_factura_service(factura_id, pagos, estado_override, datos_adicionales, usuario=None):
    """
    Registra uno o varios pagos sobre una factura.

    A diferencia de la versión anterior (un único `metodo_pago_id` +
    `monto_recibido`, siempre por el total completo de la factura), esto
    soporta:

    - **Pago dividido**: `pagos` puede traer varias entradas (ej. la mitad
      en efectivo y la mitad por Pago Móvil) en una sola venta.
    - **Abono a crédito**: si la suma de `pagos` no cubre el saldo
      pendiente de la factura, esta queda en `estado='pendiente'` con el
      saldo reducido -- se puede volver a llamar esta misma función más
      tarde con el resto (otro abono), sin volver a descontar stock.
    - **Vuelto**: si `monto_recibido` de una entrada es mayor que su
      `monto` (típicamente efectivo), el excedente queda registrado en
      `Transaccionpago.vuelto` en vez de perderse -- es el dinero que salió
      físicamente de la caja y que antes no quedaba registrado en ningún
      lado.

    Args:
        factura_id: ID de la factura.
        pagos: lista de ``{"metodo_pago_id": int, "monto": Decimal,
            "monto_recibido": Decimal opcional, "referencia": str opcional}``.
            Vacía cuando ``estado_override == "pendiente"`` (dejar la cuenta
            pendiente sin recibir dinero todavía, ej. "Pagar luego").
        estado_override: si es ``"pendiente"``, marca la factura como
            cuenta pendiente en vez de procesar pagos.
        datos_adicionales: ``{"nombre_cliente", "comentario"}`` para el caso
            "pendiente".
        usuario: usuario que está cobrando (para enlazar el pago a su turno
            de caja abierto, si tiene uno).

    Returns:
        tuple[Factura, list[Transaccionpago]]: la factura actualizada y las
        transacciones creadas (lista vacía si quedó "pendiente" sin pagos).

    Raises:
        ValueError: si la factura/método no existen, el estado es inválido,
            o los montos no tienen sentido.
    """
    try:
        factura = Factura.objects.select_for_update().get(
            id=factura_id, estado__in=["abierta", "borrador", "pendiente"],
        )
    except Factura.DoesNotExist as exc:
        raise ValueError("Factura no encontrada, ya procesada, o en un estado inválido.") from exc

    es_primer_pago = factura.estado in ("abierta", "borrador")

    # "Pagar luego": se dispone a esperar el pago, sin registrar ningún
    # ingreso de dinero todavía. Requiere un único método (el que el
    # cliente dice que usará), no una lista de pagos reales.
    if estado_override == "pendiente":
        metodo_id = datos_adicionales.get("metodo_pago_id") or (pagos[0]["metodo_pago_id"] if pagos else None)
        metodo = None
        if metodo_id:
            try:
                metodo = MetodoPago.objects.get(id=metodo_id)
            except MetodoPago.DoesNotExist as exc:
                raise ValueError("Método de pago no encontrado.") from exc

        if es_primer_pago:
            afectar_inventario_por_venta(factura)

        factura.metodo_pago = metodo
        factura.estado = "pendiente"
        factura.nombre_cliente_pendiente = datos_adicionales.get("nombre_cliente", "")
        factura.comentario_pendiente = datos_adicionales.get("comentario", "")
        # Si esto es un pedido del catálogo/B2B que llegó con
        # `pendiente_de_aprobacion=True` y el admin lo está procesando aquí
        # en vez de por "Confirmar pago" en Pedidos, ya tomó una decisión
        # real sobre él -- debe dejar de bloquear su correlativo.
        factura.pendiente_de_aprobacion = False
        factura.save()
        return factura, []

    if not pagos:
        raise ValueError("Debe indicar al menos un pago.")

    ya_pagado = Transaccionpago.objects.filter(
        factura=factura, activo=True, estado="exitoso",
    ).aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
    total_factura = factura.total or Decimal("0.00")

    caja_sesion = None
    if usuario is not None:
        caja_sesion = CajaSesion.objects.filter(usuario=usuario, activo=True).first()

    transacciones = []
    total_nuevo = Decimal("0.00")
    for entrada in pagos:
        try:
            metodo = MetodoPago.objects.get(id=entrada["metodo_pago_id"])
        except MetodoPago.DoesNotExist as exc:
            raise ValueError("Método de pago no encontrado.") from exc
        except KeyError as exc:
            raise ValueError("Cada pago debe indicar 'metodo_pago_id'.") from exc

        try:
            monto = _round(entrada["monto"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Cada pago debe indicar un 'monto' válido.") from exc
        if monto <= 0:
            raise ValueError("El monto de cada pago debe ser mayor que cero.")

        monto_recibido_raw = entrada.get("monto_recibido")
        monto_recibido = _round(monto_recibido_raw) if monto_recibido_raw not in (None, "") else monto
        if monto_recibido < monto:
            # No tiene sentido "recibir menos de lo que se está registrando
            # como pagado" -- probablemente un error de tipeo del cajero.
            monto_recibido = monto
        vuelto = _round(monto_recibido - monto)

        transaccion = Transaccionpago.objects.create(
            orden=factura.orden,
            factura=factura,
            monto=monto,
            monto_recibido=monto_recibido,
            vuelto=vuelto,
            metodo_pago=metodo,
            caja_sesion=caja_sesion,
            estado="exitoso",
            codigo_transaccion=str(uuid.uuid4()),
            referencia=(entrada.get("referencia") or "").strip() or None,
            fecha=timezone.now(),
            activo=True,
        )
        transacciones.append(transaccion)
        total_nuevo += monto

    if es_primer_pago:
        # Solo se afecta el stock la PRIMERA vez que se registra un pago
        # sobre esta factura -- una venta a crédito puede recibir varios
        # abonos después, y el stock ya se descontó en el primero.
        afectar_inventario_por_venta(factura)

    nuevo_total_pagado = ya_pagado + total_nuevo
    if len(transacciones) == 1:
        factura.metodo_pago = transacciones[0].metodo_pago

    if nuevo_total_pagado + CENT >= total_factura:
        factura.estado = "pagado"
        factura.fecha_pago = timezone.now()
    else:
        # Abono parcial: la factura sigue pendiente de cobro por el saldo
        # restante (total_factura - nuevo_total_pagado).
        factura.estado = "pendiente"
        factura.condicion_pago = "credito"

    # Idem que en la rama "pagar luego" de arriba: registrar un pago real
    # (aunque sea un abono parcial) es una decisión del admin sobre este
    # pedido -- ya no debe seguir bloqueado esperando aprobación.
    factura.pendiente_de_aprobacion = False
    factura.save()

    if factura.estado == "pagado":
        # Asiento contable automático -- OPCIONAL y completamente aislado:
        # solo hace algo si el tenant configuró una empresa contable propia
        # (ver apps.contabilidad.services.generar_asiento_automatico_venta,
        # que se traga cualquier error en silencio). Import local a
        # propósito: apps.facturacion es código compartido por TODAS las
        # verticales y no debe depender de que apps.contabilidad exista ni
        # esté instalada; este try/except es una segunda red de seguridad
        # además de la que ya tiene esa función, para que un pago que YA SE
        # PROCESÓ jamás pueda fallar por esto.
        try:
            from apps.contabilidad.services import generar_asiento_automatico_venta
            generar_asiento_automatico_venta(factura)
        except Exception:
            pass

        # Garantías automáticas -- igual de aislado que el asiento contable
        # de arriba: solo genera algo si algún producto vendido tiene
        # `meses_garantia` asignado, y nunca puede tumbar un pago que YA SE
        # PROCESÓ.
        try:
            from apps.postventa.services import generar_garantias_de_factura
            generar_garantias_de_factura(factura)
        except Exception:
            pass

    return factura, transacciones


def calcular_saldo_pendiente(factura: Factura) -> Decimal:
    """Saldo que le falta pagar a una factura (total - suma de pagos exitosos ya registrados)."""
    ya_pagado = Transaccionpago.objects.filter(
        factura=factura, activo=True, estado="exitoso",
    ).aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
    return _round((factura.total or Decimal("0.00")) - ya_pagado)


def calcular_saldo_pendiente_base(factura: Factura) -> Decimal:
    """
    Igual que `calcular_saldo_pendiente`, pero en la MONEDA BASE del tenant
    (`total_base`) -- necesario para el reporte de Cuentas por Cobrar, que
    suma facturas de clientes que pueden estar en monedas distintas. Los
    pagos (`Transaccionpago.monto`) solo se guardan en la moneda de la
    factura (no tienen su propio `monto_base`), así que se convierten aquí
    con la MISMA tasa que quedó congelada en la factura al emitirse -- un
    pago contra una factura siempre está en la moneda de esa factura, así
    que aplicar su tasa es exacto, no una aproximación.
    """
    ya_pagado = Transaccionpago.objects.filter(
        factura=factura, activo=True, estado="exitoso",
    ).aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
    tasa = factura.tasa_cambio or Decimal("1.000000")
    ya_pagado_base = ya_pagado * tasa
    return _round((factura.total_base or Decimal("0.00")) - ya_pagado_base)


def reporte_cuentas_por_cobrar(fecha_corte=None) -> list[dict]:
    """
    Agrupa por cliente las facturas a crédito con saldo pendiente > 0, con
    antigüedad de saldos (0-30/31-60/61-90/90+ días desde `fecha_operacion`
    hasta `fecha_corte`) -- el reporte clásico de "quién nos debe y desde
    hace cuánto". Solo facturas `condicion_pago='credito'` -- una venta de
    contado no genera cuenta por cobrar (se cobra en el momento).
    """
    fecha_corte = fecha_corte or timezone.now().date()
    facturas = (
        Factura.objects.filter(condicion_pago="credito", activo=True)
        .exclude(estado__iexact="anulada")
        .exclude(estado__iexact="anulado")
        .exclude(cliente__isnull=True)
        .select_related("cliente", "moneda")
    )

    por_cliente: dict[int, dict] = {}
    for factura in facturas:
        saldo = calcular_saldo_pendiente_base(factura)
        if saldo <= 0:
            continue
        fecha_op = factura.fecha_operacion.date() if hasattr(factura.fecha_operacion, "date") else factura.fecha_operacion
        dias = (fecha_corte - fecha_op).days
        bucket = "0_30" if dias <= 30 else "31_60" if dias <= 60 else "61_90" if dias <= 90 else "mas_90"

        entry = por_cliente.setdefault(factura.cliente_id, {
            "cliente_id": factura.cliente_id,
            "cliente_nombre": factura.cliente.nombre,
            "cliente_telefono": factura.cliente.telefono,
            "total": Decimal("0.00"),
            "0_30": Decimal("0.00"),
            "31_60": Decimal("0.00"),
            "61_90": Decimal("0.00"),
            "mas_90": Decimal("0.00"),
            "facturas": [],
        })
        entry["total"] += saldo
        entry[bucket] += saldo
        entry["facturas"].append({
            "id": factura.id,
            "correlativo": factura.correlativo,
            "fecha_operacion": fecha_op.isoformat(),
            "total_base": str(_round(factura.total_base)),
            "saldo_pendiente_base": str(saldo),
            "dias": dias,
            # En la moneda PROPIA de la factura (no la base) -- es lo que
            # espera `PagoView`/`procesar_pago_factura_service` al registrar
            # un cobro manual (ver `views_terminal.PagoView`), ya que
            # `Transaccionpago.monto` siempre está en la moneda de la
            # factura, nunca en la moneda base del tenant.
            "moneda_id": factura.moneda_id,
            "moneda_codigo": factura.moneda.codigo if factura.moneda else None,
            "moneda_simbolo": (factura.moneda.simbolo or factura.moneda.codigo) if factura.moneda else None,
            "saldo_pendiente": str(calcular_saldo_pendiente(factura)),
        })

    filas = list(por_cliente.values())
    for fila in filas:
        for campo in ("total", "0_30", "31_60", "61_90", "mas_90"):
            fila[campo] = str(_round(fila[campo]))
    filas.sort(key=lambda f: Decimal(f["total"]), reverse=True)
    return filas
