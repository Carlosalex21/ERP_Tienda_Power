from datetime import timedelta, date
from django.db.models import Sum, Count, Q, F, DecimalField, CharField, Value
from django.db.models.functions import Coalesce, Concat
from decimal import Decimal

# Importamos modelos de otras apps
from apps.facturacion.models import Factura, Detallefactura
from apps.clientes.models import Cliente
from apps.inventario.models import Producto, Variacionproducto

# Ventana histórica usada para estimar la velocidad de venta (unidades/día)
# de cada producto, y a cuántos días de quiebre de stock se le da la voz de
# alerta. 30 días evita que una promoción puntual de un solo día distorsione
# la proyección; 7 días de umbral da tiempo real para reabastecer antes de
# quedarse sin stock.
DIAS_VENTANA_VELOCIDAD = 30
DIAS_UMBRAL_ALERTA_QUIEBRE = 7


def obtener_prediccion_quiebre_stock():
    """
    A diferencia de "Alertas de Stock Bajo" (umbral estático sobre la
    cantidad actual), esto proyecta CUÁNTOS DÍAS le quedan a cada producto
    antes de agotarse, según su propio ritmo de venta reciente -- un
    producto con harto stock pero que se vende rápido puede quebrar antes
    que uno con poco stock pero que casi no rota, y el umbral estático no
    distingue esos dos casos.
    """
    hoy = date.today()
    desde = hoy - timedelta(days=DIAS_VENTANA_VELOCIDAD - 1)
    ventas_recientes = Detallefactura.objects.filter(
        factura__fecha_operacion__date__range=[desde, hoy],
    ).exclude(factura__estado__iexact='cancelada')

    alertas = []

    # Productos simples: el stock vive en `Producto.cantidad` y las ventas
    # se registran con `variante` vacío (una venta de variante también deja
    # `producto` seteado -- por eso se excluye explícitamente aquí, o un
    # producto variable con variantes contaría sus ventas dos veces).
    ventas_por_producto = {
        v['producto_id']: v['cantidad_total']
        for v in ventas_recientes.filter(variante__isnull=True)
            .values('producto_id')
            .annotate(cantidad_total=Coalesce(Sum('cantidad'), 0))
    }
    productos_simples = Producto.objects.filter(
        activo=True, tipo='simple', cantidad__gt=0,
    ).only('id', 'nombre', 'sku', 'cantidad')
    for producto in productos_simples:
        vendido = ventas_por_producto.get(producto.id, 0)
        _agregar_si_en_riesgo(alertas, producto.nombre, producto.sku, producto.cantidad, vendido)

    # Variantes de producto variable: el stock vive en `Variacionproducto.cantidad`.
    ventas_por_variante = {
        v['variante_id']: v['cantidad_total']
        for v in ventas_recientes.filter(variante__isnull=False)
            .values('variante_id')
            .annotate(cantidad_total=Coalesce(Sum('cantidad'), 0))
    }
    variantes = Variacionproducto.objects.filter(
        activo=True, producto__activo=True, cantidad__gt=0,
    ).select_related('producto').only('id', 'nombre', 'sku', 'cantidad', 'producto__nombre')
    for variante in variantes:
        vendido = ventas_por_variante.get(variante.id, 0)
        nombre_completo = f"{variante.producto.nombre} - {variante.nombre}" if variante.producto else variante.nombre
        _agregar_si_en_riesgo(alertas, nombre_completo, variante.sku, variante.cantidad, vendido)

    alertas.sort(key=lambda a: a['dias_restantes'])
    return alertas


def _agregar_si_en_riesgo(alertas, nombre, sku, cantidad_actual, unidades_vendidas_ventana):
    if unidades_vendidas_ventana <= 0:
        return
    velocidad_diaria = unidades_vendidas_ventana / DIAS_VENTANA_VELOCIDAD
    dias_restantes = cantidad_actual / velocidad_diaria
    if dias_restantes > DIAS_UMBRAL_ALERTA_QUIEBRE:
        return
    alertas.append({
        'nombre': nombre,
        'sku': sku,
        'cantidad': cantidad_actual,
        'venta_diaria_promedio': round(velocidad_diaria, 2),
        'dias_restantes': round(dias_restantes, 1),
    })

def obtener_metricas_dashboard(start_date_str, end_date_str, user):
    """
    Calcula todas las métricas para el panel principal:
    Resumen, Gráficos, Top Productos y Bajo Stock.
    """
    # 1. Filtro de fechas -- `date.today()`, no `timezone.now().date()`: ver
    # la nota equivalente en `apps.configuracion.services.bcv_service` sobre
    # por qué mezclar ambas puede desalinear un día el rango "últimos 30 días"
    # respecto a lo que en verdad quedó grabado en `Factura.fecha_operacion`.
    hoy = date.today()
    start_date = date.fromisoformat(start_date_str) if start_date_str else (hoy - timedelta(days=29))
    end_date = date.fromisoformat(end_date_str) if end_date_str else hoy

    base_queryset = Factura.objects.filter(fecha_operacion__date__range=[start_date, end_date])
    ventas_queryset = base_queryset.exclude(estado__iexact='cancelada')

    # 2. Tarjetas de Resumen
    resumen = ventas_queryset.aggregate(
        total_vendido=Coalesce(Sum('total'), Decimal('0.0')),
        total_pagado=Coalesce(Sum('total', filter=Q(estado__iexact='pagado')), Decimal('0.0')),
        total_pendiente=Coalesce(Sum('total', filter=Q(estado__iexact='pendiente')), Decimal('0.0')),
        num_transacciones=Count('id')
    )

    # 2.1. Variación vs. el período inmediatamente anterior, de la misma
    # duración (ej. si el rango son los últimos 30 días, se compara contra
    # los 30 días antes de esos) -- antes el frontend mostraba un "+12%"
    # fijo en el dashboard que no salía de ningún cálculo real.
    periodo_dias = (end_date - start_date).days + 1
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=periodo_dias - 1)
    total_vendido_anterior = Factura.objects.filter(
        fecha_operacion__date__range=[prev_start, prev_end],
    ).exclude(estado__iexact='cancelada').aggregate(
        total=Coalesce(Sum('total'), Decimal('0.0')),
    )['total']

    total_vendido_actual = resumen['total_vendido']
    if total_vendido_anterior > 0:
        variacion_ventas_pct = float((total_vendido_actual - total_vendido_anterior) / total_vendido_anterior * 100)
    elif total_vendido_actual > 0:
        # No hubo ventas en el período anterior pero sí en este: hay
        # variación real (de 0 a algo), pero un porcentaje no está definido
        # matemáticamente -- se reporta `None` y el frontend simplemente
        # omite el badge en vez de inventar un número.
        variacion_ventas_pct = None
    else:
        variacion_ventas_pct = None
    resumen['variacion_ventas_pct'] = variacion_ventas_pct

    # 3. Gráfico de Ventas Diarias
    ventas_por_dia_qs = ventas_queryset.values('fecha_operacion__date').annotate(
        total=Coalesce(Sum('total'), Decimal('0.0'))
    ).order_by('fecha_operacion__date')

    sales_map = {item['fecha_operacion__date']: item['total'] for item in ventas_por_dia_qs}
    all_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    grafico_ventas = {
        'labels': [d.strftime('%d/%m') for d in all_dates],
        'data': [float(sales_map.get(d, 0)) for d in all_dates]
    }

    # 4. Productos más vendidos (cantidad E ingresos -- antes solo se
    # calculaba la cantidad, pero el frontend también quería mostrar cuánto
    # generó cada producto en el período).
    productos_mas_vendidos = list(
        Detallefactura.objects.filter(factura__in=ventas_queryset)
        .values('producto__nombre', 'variante__nombre')
        .annotate(
            cantidad_total=Coalesce(Sum('cantidad'), 0),
            ingresos_total=Coalesce(
                Sum(F('cantidad') * F('precio_unitario'), output_field=DecimalField()),
                Decimal('0.0'),
            ),
        )
        .order_by('-cantidad_total')[:5]
    )

    # 5. Bajo Stock: se guarda tanto el TOTAL real (para la tarjeta de
    # conteo) como los primeros 5 (para la lista) -- antes el frontend usaba
    # `len(lista_top_5)` como si fuera el total, subestimando el conteo en
    # cuanto había más de 5 productos con stock bajo.
    #
    # Usa el umbral propio del producto (`stock_minimo`) cuando está
    # definido -- antes el umbral de "bajo stock" era un `10` fijo para
    # TODO el catálogo, sin sentido para un negocio que vende a la vez
    # tornillos (bajo stock a los 500) y electrodomésticos (bajo stock a
    # los 2). Sin `stock_minimo` asignado, se sigue usando el `10` general.
    UMBRAL_BAJO_STOCK_GENERAL = 10
    # `tipo='servicio'` no tiene stock real (siempre cantidad=0/None) -- sin
    # excluirlo, CADA servicio aparecía como "bajo stock" en el dashboard.
    bajo_stock_qs = Producto.objects.filter(activo=True).exclude(tipo='servicio').filter(
        Q(stock_minimo__isnull=False, cantidad__lt=F('stock_minimo')) |
        Q(stock_minimo__isnull=True, cantidad__lt=UMBRAL_BAJO_STOCK_GENERAL)
    ).order_by('cantidad')
    bajo_stock_total = bajo_stock_qs.count()
    bajo_stock = list(bajo_stock_qs.values('nombre', 'cantidad')[:5])

    # 6. Valor de inventario: COSTO (`costo_promedio`) × cantidad de cada
    # producto activo -- no `precio` (precio de VENTA al público). Antes se
    # usaba `precio`, lo que en realidad calculaba "cuánto valdría el
    # inventario si se vendiera todo hoy" en vez de "cuánto costó lo que
    # tengo en stock" (que es lo que la propia tarjeta del dashboard dice
    # mostrar: "Costo total de tu stock actual") -- con productos de buen
    # margen esto inflaba el valor mostrado varias veces por encima del
    # real. Para productos de tipo 'variable' el costo/cantidad reales viven
    # en cada variante, no en el producto padre -- se suman ambas fuentes
    # para no subestimar el valor de un catálogo con productos variables.
    from apps.inventario.models import Variacionproducto

    valor_productos_simples = Producto.objects.filter(activo=True).exclude(tipo='variable').aggregate(
        valor=Coalesce(
            Sum(F('costo_promedio') * F('cantidad'), output_field=DecimalField()),
            Decimal('0.0'),
        )
    )['valor']
    valor_variantes = Variacionproducto.objects.filter(producto__activo=True).aggregate(
        valor=Coalesce(
            Sum(F('costo_promedio') * F('cantidad'), output_field=DecimalField()),
            Decimal('0.0'),
        )
    )['valor']
    valor_inventario = valor_productos_simples + valor_variantes

    return {
        'userInfo': {'nombre': user.get_full_name() or user.username},
        'resumen': resumen,
        'graficoVentas': grafico_ventas,
        'productosMasVendidos': productos_mas_vendidos,
        'productosBajoStock': bajo_stock,
        'prediccionQuiebreStock': obtener_prediccion_quiebre_stock(),
        'infoGeneral': {
            'clientes': Cliente.objects.filter(activo=True).count(),
            'productos': Producto.objects.filter(activo=True).count(),
            'ordenes_periodo': ventas_queryset.count(),
            'valor_inventario': valor_inventario,
            'productos_bajo_stock_count': bajo_stock_total,
        }
    }