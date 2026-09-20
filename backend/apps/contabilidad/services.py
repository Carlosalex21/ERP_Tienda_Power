"""Servicios de negocio del módulo de Contabilidad: asientos, libro mayor, balance de comprobación y estados financieros."""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from .models import (
    EmpresaContable, CuentaContable, AsientoContable, AsientoContableDetalle,
    AsientoPlantilla, AsientoPlantillaLinea, CierreEjercicio,
)

CENT = Decimal('0.01')

NATURALEZA_POR_TIPO = {
    'activo': 'deudora',
    'gasto': 'deudora',
    'costo': 'deudora',
    'pasivo': 'acreedora',
    'patrimonio': 'acreedora',
    'ingreso': 'acreedora',
}

# Plan de cuentas base (esqueleto genérico LatAm) que se siembra al crear una
# empresa contable, para que el contador no arranque de una pantalla vacía
# sin saber por dónde empezar -- puede agregar/editar cuentas libremente
# después, esto es solo un punto de partida razonable.
PLAN_CUENTAS_DEFAULT = [
    # (codigo, nombre, tipo, acepta_movimiento, codigo_padre)
    ('1', 'ACTIVO', 'activo', False, None),
    ('1.1', 'Activo Corriente', 'activo', False, '1'),
    ('1.1.01', 'Caja', 'activo', True, '1.1'),
    ('1.1.02', 'Bancos', 'activo', True, '1.1'),
    ('1.1.03', 'Cuentas por Cobrar Clientes', 'activo', True, '1.1'),
    ('1.1.04', 'Inventario', 'activo', True, '1.1'),
    ('1.1.05', 'IVA Crédito Fiscal', 'activo', True, '1.1'),
    ('1.2', 'Activo No Corriente', 'activo', False, '1'),
    ('1.2.01', 'Mobiliario y Equipos', 'activo', True, '1.2'),
    ('1.2.02', 'Depreciación Acumulada', 'activo', True, '1.2'),
    ('2', 'PASIVO', 'pasivo', False, None),
    ('2.1', 'Pasivo Corriente', 'pasivo', False, '2'),
    ('2.1.01', 'Cuentas por Pagar Proveedores', 'pasivo', True, '2.1'),
    ('2.1.02', 'IVA Débito Fiscal', 'pasivo', True, '2.1'),
    ('2.1.03', 'Retenciones por Pagar', 'pasivo', True, '2.1'),
    ('2.1.04', 'Sueldos y Salarios por Pagar', 'pasivo', True, '2.1'),
    ('3', 'PATRIMONIO', 'patrimonio', False, None),
    ('3.1', 'Capital Social', 'patrimonio', True, '3'),
    ('3.2', 'Utilidades Retenidas', 'patrimonio', True, '3'),
    ('3.3', 'Utilidad del Ejercicio', 'patrimonio', True, '3'),
    ('4', 'INGRESOS', 'ingreso', False, None),
    ('4.1', 'Ingresos por Ventas', 'ingreso', True, '4'),
    ('4.2', 'Ingresos por Honorarios', 'ingreso', True, '4'),
    ('4.3', 'Otros Ingresos', 'ingreso', True, '4'),
    ('5', 'COSTOS', 'costo', False, None),
    ('5.1', 'Costo de Ventas', 'costo', True, '5'),
    ('6', 'GASTOS', 'gasto', False, None),
    ('6.1', 'Gastos de Administración', 'gasto', False, '6'),
    ('6.1.01', 'Sueldos y Salarios', 'gasto', True, '6.1'),
    ('6.1.02', 'Alquiler', 'gasto', True, '6.1'),
    ('6.1.03', 'Servicios (Luz, Agua, Internet)', 'gasto', True, '6.1'),
    ('6.1.04', 'Honorarios Profesionales', 'gasto', True, '6.1'),
    ('6.1.05', 'Depreciación', 'gasto', True, '6.1'),
    ('6.2', 'Gastos de Venta', 'gasto', False, '6'),
    ('6.2.01', 'Publicidad y Mercadeo', 'gasto', True, '6.2'),
    ('6.3', 'Gastos Financieros', 'gasto', False, '6'),
    ('6.3.01', 'Comisiones e Intereses Bancarios', 'gasto', True, '6.3'),
]


def seed_plan_cuentas_default(empresa: EmpresaContable) -> None:
    por_codigo: dict[str, CuentaContable] = {}
    for codigo, nombre, tipo, acepta_movimiento, codigo_padre in PLAN_CUENTAS_DEFAULT:
        cuenta = CuentaContable.objects.create(
            empresa=empresa,
            codigo=codigo,
            nombre=nombre,
            tipo=tipo,
            naturaleza=NATURALEZA_POR_TIPO[tipo],
            acepta_movimiento=acepta_movimiento,
            cuenta_padre=por_codigo.get(codigo_padre) if codigo_padre else None,
        )
        por_codigo[codigo] = cuenta


class AsientoContableError(Exception):
    """Error controlado al crear/anular un asiento contable."""


def _round(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


@transaction.atomic
def crear_asiento_contable(
    empresa: EmpresaContable,
    fecha,
    descripcion: str,
    lineas: list[dict],
    usuario,
    estado: str = 'contabilizado',
    origen: str = 'manual',
    comprobante=None,
) -> AsientoContable:
    """
    Crea un asiento contable completo (cabecera + líneas) de una vez --
    valida la partida doble ANTES de escribir nada: la suma de los débitos
    debe ser igual a la suma de los créditos, cada línea debe tener
    exactamente uno de los dos (nunca ambos, ni ninguno), y se necesitan al
    menos 2 líneas (un asiento de una sola cuenta no tiene contrapartida).

    `estado='borrador'` guarda el asiento SIN que cuente todavía en ningún
    reporte (libro mayor/balance/estados filtran `estado='contabilizado'`)
    -- para que el contador pueda revisarlo antes de darlo por bueno.
    """
    if estado not in ('borrador', 'contabilizado'):
        raise AsientoContableError('Estado inválido para un asiento nuevo.')
    if len(lineas) < 2:
        raise AsientoContableError('Un asiento necesita al menos 2 líneas (la cuenta y su contrapartida).')

    total_debe = Decimal('0.00')
    total_haber = Decimal('0.00')
    cuentas_ids = [l['cuenta_id'] for l in lineas]
    cuentas_por_id = {
        c.id: c for c in CuentaContable.objects.filter(pk__in=cuentas_ids, empresa=empresa, activo=True)
    }
    for linea in lineas:
        cuenta = cuentas_por_id.get(linea['cuenta_id'])
        if cuenta is None:
            raise AsientoContableError('Una o más cuentas seleccionadas no existen en esta empresa.')
        if not cuenta.acepta_movimiento:
            raise AsientoContableError(f'La cuenta "{cuenta.codigo} - {cuenta.nombre}" es de grupo y no acepta movimientos directos.')
        debe = _round(linea.get('debe') or 0)
        haber = _round(linea.get('haber') or 0)
        if (debe > 0) == (haber > 0):
            raise AsientoContableError(f'La línea de "{cuenta.nombre}" debe tener un monto en Debe O en Haber, no ambos ni ninguno.')
        total_debe += debe
        total_haber += haber

    if total_debe != total_haber:
        raise AsientoContableError(
            f'El asiento no cuadra: Debe {total_debe} ≠ Haber {total_haber}.'
        )
    if total_debe == 0:
        raise AsientoContableError('El asiento no puede estar en cero.')

    asiento = AsientoContable.objects.create(
        empresa=empresa, fecha=fecha, descripcion=descripcion, usuario=usuario,
        estado=estado, origen=origen, comprobante=comprobante,
    )
    for orden, linea in enumerate(lineas):
        AsientoContableDetalle.objects.create(
            asiento=asiento,
            cuenta=cuentas_por_id[linea['cuenta_id']],
            debe=_round(linea.get('debe') or 0),
            haber=_round(linea.get('haber') or 0),
            descripcion=linea.get('descripcion') or '',
            orden=orden,
        )
    return asiento


def anular_asiento_contable(asiento: AsientoContable) -> None:
    """No se borra un asiento contabilizado (rompería el historial/numeración) -- se anula, igual que una factura."""
    if asiento.estado == 'anulado':
        raise AsientoContableError('Este asiento ya está anulado.')
    asiento.estado = 'anulado'
    asiento.fecha_anulacion = timezone.now()
    asiento.save(update_fields=['estado', 'fecha_anulacion'])


def contabilizar_asiento_borrador(asiento: AsientoContable) -> None:
    """Promueve un borrador a contabilizado -- recién ahí empieza a contar en libro mayor/balance/estados."""
    if asiento.estado != 'borrador':
        raise AsientoContableError('Solo un asiento en borrador se puede contabilizar.')
    total_debe = sum((d.debe for d in asiento.detalles.all()), Decimal('0.00'))
    total_haber = sum((d.haber for d in asiento.detalles.all()), Decimal('0.00'))
    if total_debe != total_haber:
        raise AsientoContableError(f'El asiento no cuadra: Debe {total_debe} ≠ Haber {total_haber}.')
    asiento.estado = 'contabilizado'
    asiento.save(update_fields=['estado'])


def libro_mayor(empresa: EmpresaContable, cuenta: CuentaContable, fecha_desde=None, fecha_hasta=None) -> dict:
    """
    Movimientos de UNA cuenta en el rango de fechas, con saldo corriente --
    el reporte clásico de "libro mayor" que un contador usa para auditar
    una cuenta específica.
    """
    detalles = AsientoContableDetalle.objects.filter(
        cuenta=cuenta, asiento__empresa=empresa, asiento__estado='contabilizado',
    ).select_related('asiento').order_by('asiento__fecha', 'asiento__numero', 'orden')
    if fecha_desde:
        detalles = detalles.filter(asiento__fecha__gte=fecha_desde)
    if fecha_hasta:
        detalles = detalles.filter(asiento__fecha__lte=fecha_hasta)

    es_deudora = cuenta.naturaleza == 'deudora'
    saldo = Decimal('0.00')
    movimientos = []
    for d in detalles:
        saldo += (d.debe - d.haber) if es_deudora else (d.haber - d.debe)
        movimientos.append({
            'asiento_id': d.asiento_id,
            'asiento_numero': d.asiento.numero,
            'fecha': d.asiento.fecha,
            'descripcion': d.descripcion or d.asiento.descripcion,
            'debe': str(d.debe),
            'haber': str(d.haber),
            'saldo': str(_round(saldo)),
        })
    return {
        'cuenta': {'id': cuenta.id, 'codigo': cuenta.codigo, 'nombre': cuenta.nombre},
        'movimientos': movimientos,
        'saldo_final': str(_round(saldo)),
    }


def balance_comprobacion(empresa: EmpresaContable, fecha_desde=None, fecha_hasta=None) -> list[dict]:
    """
    Suma de débitos/créditos y saldo neto por cada cuenta con movimiento en
    el período -- el reporte que confirma que la contabilidad sigue
    cuadrada (total Debe == total Haber en TODA la empresa).
    """
    qs = AsientoContableDetalle.objects.filter(
        asiento__empresa=empresa, asiento__estado='contabilizado',
    )
    if fecha_desde:
        qs = qs.filter(asiento__fecha__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(asiento__fecha__lte=fecha_hasta)

    agregados = (
        qs.values('cuenta_id', 'cuenta__codigo', 'cuenta__nombre', 'cuenta__naturaleza')
        .annotate(total_debe=Sum('debe'), total_haber=Sum('haber'))
        .order_by('cuenta__codigo')
    )
    filas = []
    for a in agregados:
        debe = a['total_debe'] or Decimal('0.00')
        haber = a['total_haber'] or Decimal('0.00')
        saldo = (debe - haber) if a['cuenta__naturaleza'] == 'deudora' else (haber - debe)
        filas.append({
            'cuenta_id': a['cuenta_id'],
            'codigo': a['cuenta__codigo'],
            'nombre': a['cuenta__nombre'],
            'debe': str(_round(debe)),
            'haber': str(_round(haber)),
            'saldo': str(_round(saldo)),
        })
    return filas


def estados_financieros(empresa: EmpresaContable, fecha_desde=None, fecha_hasta=None) -> dict:
    """
    Balance General (Activo / Pasivo / Patrimonio, a la fecha de corte) y
    Estado de Resultados (Ingresos - Costos - Gastos, del período) --
    derivados de `balance_comprobacion` agrupando por `cuenta.tipo`.
    """
    filas = balance_comprobacion(empresa, fecha_desde, fecha_hasta)
    ids = [f['cuenta_id'] for f in filas]
    tipos_por_cuenta = dict(CuentaContable.objects.filter(pk__in=ids).values_list('id', 'tipo'))

    grupos: dict[str, list[dict]] = {t: [] for t, _ in CuentaContable.TIPO_CHOICES}
    for f in filas:
        tipo = tipos_por_cuenta.get(f['cuenta_id'])
        if tipo:
            grupos[tipo].append(f)

    def total(tipo: str) -> Decimal:
        return sum((Decimal(f['saldo']) for f in grupos[tipo]), Decimal('0.00'))

    total_activo = total('activo')
    total_pasivo = total('pasivo')
    total_patrimonio = total('patrimonio')
    total_ingresos = total('ingreso')
    total_costos = total('costo')
    total_gastos = total('gasto')
    utilidad_periodo = _round(total_ingresos - total_costos - total_gastos)

    return {
        'balance_general': {
            'activo': grupos['activo'],
            'pasivo': grupos['pasivo'],
            'patrimonio': grupos['patrimonio'],
            'total_activo': str(_round(total_activo)),
            'total_pasivo': str(_round(total_pasivo)),
            'total_patrimonio': str(_round(total_patrimonio)),
            'utilidad_periodo': str(utilidad_periodo),
            # Activo = Pasivo + Patrimonio + Utilidad del período (todavía no
            # cerrada a Patrimonio) -- si esto no cuadra, algo en los
            # asientos está mal (una partida doble mal armada en algún lado).
            'cuadra': _round(total_activo) == _round(total_pasivo + total_patrimonio + utilidad_periodo),
        },
        'estado_resultados': {
            'ingresos': grupos['ingreso'],
            'costos': grupos['costo'],
            'gastos': grupos['gasto'],
            'total_ingresos': str(_round(total_ingresos)),
            'total_costos': str(_round(total_costos)),
            'total_gastos': str(_round(total_gastos)),
            'utilidad_periodo': str(utilidad_periodo),
        },
    }


class FacturarHonorariosError(Exception):
    """Error controlado al facturar honorarios profesionales a una empresa."""


@transaction.atomic
def facturar_honorarios_empresa(
    empresa: EmpresaContable,
    lineas: list[dict],
    metodo_pago_id: int,
    cuenta_cobro_id: int,
    cuenta_ingreso_id: int,
    usuario,
    condicion_pago: str = 'contado',
    moneda_id: int | None = None,
):
    """
    El contador le factura sus honorarios profesionales a una empresa (la
    misma factura que vería el `Cliente` enlazado) Y, de una vez, genera el
    asiento contable correspondiente en ESA empresa -- sin esto, facturar y
    contabilizar quedaban como dos mundos separados que el contador tenía
    que reconciliar a mano cada vez.

    `lineas` es una lista de `{producto_id, cantidad, monto}` -- cada
    producto debe ser un ítem tipo='servicio' del catálogo (ej. "Honorarios
    Profesionales", "Declaración de ISLR"), igual que en
    `apps.servicios.services.cerrar_orden_servicio`.

    `cuenta_cobro_id`/`cuenta_ingreso_id` son cuentas DE ESTA EMPRESA: a
    cuál se debita el cobro (Caja/Banco/Cuentas por Cobrar) y a cuál se
    acredita el ingreso -- el contador las elige porque solo él sabe cómo
    quiere clasificar esto en su plan de cuentas.

    Returns:
        tuple[Factura, AsientoContable | None]: la factura creada y el
        asiento generado (``None`` si no se pudo generar porque las cuentas
        indicadas no son válidas -- la factura igual se emite; no tiene
        sentido bloquear el cobro real por un problema de clasificación
        contable que se puede corregir después con un asiento manual).
    """
    from apps.clientes.models import Cliente
    from apps.configuracion.models import Moneda
    from apps.facturacion.models import Factura, Detallefactura
    from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura
    from apps.facturacion.services.pagos_service import procesar_pago_factura_service
    from apps.inventario.models import Almacen, Producto

    if empresa.cliente_id is None:
        raise FacturarHonorariosError(
            'Esta empresa no tiene un cliente vinculado -- edítala y enlaza un cliente antes de facturarle honorarios.'
        )
    if not lineas:
        raise FacturarHonorariosError('Agrega al menos un concepto para facturar.')

    productos_por_id = {
        p.id: p for p in Producto.objects.filter(pk__in=[l['producto_id'] for l in lineas], activo=True)
    }
    faltantes = [l['producto_id'] for l in lineas if l['producto_id'] not in productos_por_id]
    if faltantes:
        raise FacturarHonorariosError('Uno o más conceptos seleccionados no existen.')

    moneda_base = Moneda.objects.filter(es_predeterminada=True).first()
    moneda = Moneda.objects.filter(pk=moneda_id).first() if moneda_id else None
    if moneda is None:
        moneda = moneda_base
    almacen = Almacen.objects.first()

    factura = Factura.objects.create(
        usuario=usuario,
        vendedor=usuario,
        condicion_pago=condicion_pago,
        cliente=empresa.cliente,
        fecha_operacion=timezone.now(),
        moneda=moneda,
        almacen=almacen,
        estado='abierta',
    )
    for linea in lineas:
        Detallefactura.objects.create(
            factura=factura,
            producto=productos_por_id[linea['producto_id']],
            cantidad=linea.get('cantidad', 1),
            precio_unitario=linea['monto'],
        )
    recalcular_y_guardar_factura(factura)

    pagos = [{
        "metodo_pago_id": metodo_pago_id,
        "monto": factura.total,
        "monto_recibido": factura.total,
    }]
    try:
        factura, _transacciones = procesar_pago_factura_service(
            factura_id=factura.id,
            pagos=pagos,
            estado_override='',
            datos_adicionales={},
            usuario=usuario,
        )
    except ValueError as exc:
        raise FacturarHonorariosError(str(exc)) from exc

    # Asiento automático: Debe la cuenta de cobro (Caja/Banco/CxC) por el
    # total, Haber la cuenta de ingreso -- separando el IVA en su propia
    # cuenta (pasivo, no ingreso) cuando la factura lo tiene, para que el
    # asiento quede fiscalmente correcto y no solo "cuadrado a secas".
    asiento = None
    cuenta_cobro = CuentaContable.objects.filter(pk=cuenta_cobro_id, empresa=empresa, acepta_movimiento=True).first()
    cuenta_ingreso = CuentaContable.objects.filter(pk=cuenta_ingreso_id, empresa=empresa, acepta_movimiento=True).first()
    if cuenta_cobro and cuenta_ingreso:
        lineas_asiento = [{'cuenta_id': cuenta_cobro.id, 'debe': factura.total, 'haber': 0}]
        cuenta_iva = CuentaContable.objects.filter(
            empresa=empresa, tipo='pasivo', codigo__icontains='2.1.02', acepta_movimiento=True,
        ).first()
        if cuenta_iva and factura.iva_total and factura.iva_total > 0:
            lineas_asiento.append({'cuenta_id': cuenta_ingreso.id, 'debe': 0, 'haber': factura.base_imponible})
            lineas_asiento.append({'cuenta_id': cuenta_iva.id, 'debe': 0, 'haber': factura.iva_total})
        else:
            lineas_asiento.append({'cuenta_id': cuenta_ingreso.id, 'debe': 0, 'haber': factura.total})
        try:
            asiento = crear_asiento_contable(
                empresa=empresa,
                fecha=timezone.now().date(),
                descripcion=f'Honorarios facturados a {empresa.cliente.nombre} ({factura.correlativo or f"#{factura.id}"})',
                lineas=lineas_asiento,
                usuario=usuario,
                origen='honorarios',
            )
        except AsientoContableError:
            # La factura ya está emitida y cobrada -- si el asiento no
            # cuadra por algo raro en las cuentas, se deja para que el
            # contador lo registre manualmente en vez de perder el cobro.
            asiento = None

    return factura, asiento


# --- Cierre de Ejercicio ---

def cerrar_ejercicio(
    empresa: EmpresaContable,
    fecha_desde,
    fecha_hasta,
    cuenta_patrimonio_id: int,
    usuario,
) -> AsientoContable:
    """
    Cierra un período: deja en cero las cuentas de Ingreso/Costo/Gasto que
    tuvieron movimiento en el rango (un asiento inverso por cada una) y
    manda la diferencia neta (utilidad o pérdida) a una cuenta de
    Patrimonio -- el cierre contable clásico de fin de ejercicio.

    No se puede cerrar el mismo rango dos veces (ver `CierreEjercicio`,
    único registro de que ya se hizo).
    """
    if CierreEjercicio.objects.filter(empresa=empresa, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta).exists():
        raise AsientoContableError('Ya existe un cierre registrado para este período exacto.')

    cuenta_patrimonio = CuentaContable.objects.filter(
        pk=cuenta_patrimonio_id, empresa=empresa, acepta_movimiento=True, tipo='patrimonio',
    ).first()
    if cuenta_patrimonio is None:
        raise AsientoContableError('La cuenta de patrimonio seleccionada no es válida para esta empresa.')

    filas = balance_comprobacion(empresa, fecha_desde, fecha_hasta)
    ids = [f['cuenta_id'] for f in filas]
    cuentas_por_id = {c.id: c for c in CuentaContable.objects.filter(pk__in=ids)}

    lineas: list[dict] = []
    utilidad = Decimal('0.00')
    for f in filas:
        cuenta = cuentas_por_id.get(f['cuenta_id'])
        if cuenta is None or cuenta.tipo not in ('ingreso', 'costo', 'gasto'):
            continue
        saldo = Decimal(f['saldo'])
        if saldo == 0:
            continue
        if cuenta.naturaleza == 'acreedora':
            # Ingreso con saldo acreedor -- se debita para dejarlo en cero.
            lineas.append({'cuenta_id': cuenta.id, 'debe': saldo, 'haber': 0})
            utilidad += saldo
        else:
            # Costo/Gasto con saldo deudor -- se acredita para dejarlo en cero.
            lineas.append({'cuenta_id': cuenta.id, 'debe': 0, 'haber': saldo})
            utilidad -= saldo

    if not lineas:
        raise AsientoContableError('No hay movimientos de Ingresos/Costos/Gastos en este período para cerrar.')

    if utilidad > 0:
        lineas.append({'cuenta_id': cuenta_patrimonio.id, 'debe': 0, 'haber': utilidad})
    elif utilidad < 0:
        lineas.append({'cuenta_id': cuenta_patrimonio.id, 'debe': -utilidad, 'haber': 0})

    asiento = crear_asiento_contable(
        empresa=empresa,
        fecha=fecha_hasta,
        descripcion=f'Cierre de ejercicio {fecha_desde} a {fecha_hasta}',
        lineas=lineas,
        usuario=usuario,
        origen='cierre',
    )
    CierreEjercicio.objects.create(
        empresa=empresa, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, asiento=asiento, usuario=usuario,
    )
    return asiento


# --- Plantillas de Asiento ---

@transaction.atomic
def crear_plantilla_desde_asiento(asiento: AsientoContable, nombre: str) -> AsientoPlantilla:
    """Guarda la estructura de un asiento ya existente como plantilla reutilizable."""
    plantilla = AsientoPlantilla.objects.create(
        empresa=asiento.empresa, nombre=nombre, descripcion_asiento=asiento.descripcion,
    )
    for detalle in asiento.detalles.all():
        AsientoPlantillaLinea.objects.create(
            plantilla=plantilla, cuenta=detalle.cuenta, debe=detalle.debe, haber=detalle.haber,
            descripcion=detalle.descripcion, orden=detalle.orden,
        )
    return plantilla


# --- Conciliación Bancaria ---

def conciliacion_bancaria(empresa: EmpresaContable, cuenta: CuentaContable, fecha_hasta=None) -> dict:
    """
    Movimientos de una cuenta de Caja/Banco con su estado de conciliación --
    el contador marca cuáles ya cruzó contra el estado de cuenta real, y
    esto muestra el saldo según libros vs. el saldo ya conciliado, para que
    la diferencia (lo pendiente de conciliar) salte a la vista.
    """
    detalles = AsientoContableDetalle.objects.filter(
        cuenta=cuenta, asiento__empresa=empresa, asiento__estado='contabilizado',
    ).select_related('asiento').order_by('asiento__fecha', 'asiento__numero')
    if fecha_hasta:
        detalles = detalles.filter(asiento__fecha__lte=fecha_hasta)

    es_deudora = cuenta.naturaleza == 'deudora'
    saldo_libros = Decimal('0.00')
    saldo_conciliado = Decimal('0.00')
    movimientos = []
    for d in detalles:
        monto_neto = (d.debe - d.haber) if es_deudora else (d.haber - d.debe)
        saldo_libros += monto_neto
        if d.conciliado:
            saldo_conciliado += monto_neto
        movimientos.append({
            'detalle_id': d.id,
            'asiento_id': d.asiento_id,
            'asiento_numero': d.asiento.numero,
            'fecha': d.asiento.fecha,
            'descripcion': d.descripcion or d.asiento.descripcion,
            'debe': str(d.debe),
            'haber': str(d.haber),
            'conciliado': d.conciliado,
            'fecha_conciliacion': d.fecha_conciliacion,
        })
    return {
        'cuenta': {'id': cuenta.id, 'codigo': cuenta.codigo, 'nombre': cuenta.nombre},
        'movimientos': movimientos,
        'saldo_libros': str(_round(saldo_libros)),
        'saldo_conciliado': str(_round(saldo_conciliado)),
        'diferencia': str(_round(saldo_libros - saldo_conciliado)),
    }


def marcar_conciliado(detalle_id: int, empresa: EmpresaContable, conciliado: bool) -> None:
    detalle = AsientoContableDetalle.objects.filter(
        pk=detalle_id, asiento__empresa=empresa,
    ).select_related('asiento').first()
    if detalle is None:
        raise AsientoContableError('Movimiento no encontrado en esta empresa.')
    detalle.conciliado = conciliado
    detalle.fecha_conciliacion = timezone.now().date() if conciliado else None
    detalle.save(update_fields=['conciliado', 'fecha_conciliacion'])


# --- Asiento automático desde una venta normal del sistema (POS, catálogo,
# servicios, restaurante...) -- solo si el tenant marcó una EmpresaContable
# como "es_negocio_propio" y configuró sus cuentas por defecto. ---

def obtener_metricas_dashboard_contador() -> dict:
    """
    Métricas del dashboard principal para tenants tipo_negocio='contador' --
    ese vertical no vende bienes físicos, así que las tarjetas genéricas de
    inventario/stock del dashboard no le dicen nada; estas sí (ver
    `apps.reportes.api.views_dashboard.DashboardDataView`, que agrega esto
    al payload solo para ese vertical).
    """
    hoy = timezone.now().date()
    clientes_ids = EmpresaContable.objects.filter(
        activo=True, cliente__isnull=False,
    ).values_list('cliente_id', flat=True)

    from apps.facturacion.models import Factura

    honorarios_facturados_mes = Factura.objects.filter(
        cliente_id__in=clientes_ids, fecha_operacion__year=hoy.year, fecha_operacion__month=hoy.month,
    ).exclude(estado__iexact='cancelada').aggregate(
        total=Sum('total'),
    )['total'] or Decimal('0.00')

    return {
        'empresas_activas': EmpresaContable.objects.filter(activo=True).count(),
        'asientos_contabilizados_mes': AsientoContable.objects.filter(
            estado='contabilizado', fecha__year=hoy.year, fecha__month=hoy.month,
        ).count(),
        'honorarios_facturados_mes': str(_round(honorarios_facturados_mes)),
        'cierres_realizados': CierreEjercicio.objects.count(),
    }


def generar_asiento_automatico_venta(factura) -> AsientoContable | None:
    """
    Se llama DESPUÉS de que una venta ya se cobró con éxito
    (`procesar_pago_factura_service`) -- nunca debe poder tumbar ni revertir
    la venta: cualquier problema (no hay empresa propia configurada, faltan
    cuentas, lo que sea) se traga en silencio y simplemente no genera
    asiento. El contador siempre puede registrarlo a mano después.
    """
    try:
        empresa = EmpresaContable.objects.filter(
            es_negocio_propio=True, activo=True,
            cuenta_cobro_default__isnull=False, cuenta_ingreso_default__isnull=False,
        ).select_related('cuenta_cobro_default', 'cuenta_ingreso_default', 'cuenta_iva_default').first()
        if empresa is None:
            return None

        total = factura.total or Decimal('0.00')
        if total <= 0:
            return None

        lineas = [{'cuenta_id': empresa.cuenta_cobro_default_id, 'debe': total, 'haber': 0}]
        if empresa.cuenta_iva_default_id and factura.iva_total and factura.iva_total > 0:
            lineas.append({'cuenta_id': empresa.cuenta_ingreso_default_id, 'debe': 0, 'haber': factura.base_imponible})
            lineas.append({'cuenta_id': empresa.cuenta_iva_default_id, 'debe': 0, 'haber': factura.iva_total})
        else:
            lineas.append({'cuenta_id': empresa.cuenta_ingreso_default_id, 'debe': 0, 'haber': total})

        return crear_asiento_contable(
            empresa=empresa,
            fecha=timezone.now().date(),
            descripcion=f'Venta {factura.correlativo or f"#{factura.id}"}',
            lineas=lineas,
            usuario=getattr(factura, 'usuario', None),
            origen='venta',
        )
    except Exception:
        # Fallar en silencio a propósito -- ver docstring. Se loguea para
        # que el contador pueda darse cuenta y registrar el asiento a mano,
        # pero JAMÁS debe tumbar el flujo de cobro que ya se completó.
        import logging
        logging.getLogger(__name__).warning('No se pudo generar el asiento automático de la venta %s', getattr(factura, 'id', '?'), exc_info=True)
        return None
