from datetime import timedelta, date
from django.utils import timezone
from django.db.models import Sum, Count, Q, F, DecimalField, CharField, Value
from django.db.models.functions import Coalesce, Concat
from decimal import Decimal

# Importamos modelos de otras apps
from apps.facturacion.models import Factura, Detallefactura
from apps.clientes.models import Cliente
from apps.inventario.models import Producto

def obtener_metricas_dashboard(start_date_str, end_date_str, user):
    """
    Calcula todas las métricas para el panel principal:
    Resumen, Gráficos, Top Productos y Bajo Stock.
    """
    # 1. Filtro de fechas
    hoy = timezone.now().date()
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

    # 4. Productos más vendidos
    productos_mas_vendidos = list(
        Detallefactura.objects.filter(factura__in=ventas_queryset)
        .values('producto__nombre', 'variante__nombre')
        .annotate(cantidad_total=Coalesce(Sum('cantidad'), 0))
        .order_by('-cantidad_total')[:5]
    )

    # 5. Bajo Stock
    bajo_stock = list(
        Producto.objects.filter(cantidad__lt=10, activo=True)
        .order_by('cantidad')
        .values('nombre', 'cantidad')[:5]
    )

    return {
        'userInfo': {'nombre': user.get_full_name() or user.username},
        'resumen': resumen,
        'graficoVentas': grafico_ventas,
        'productosMasVendidos': productos_mas_vendidos,
        'productosBajoStock': bajo_stock,
        'infoGeneral': {
            'clientes': Cliente.objects.filter(activo=True).count(),
            'productos': Producto.objects.filter(activo=True).count(),
            'ordenes_periodo': ventas_queryset.count()
        }
    }