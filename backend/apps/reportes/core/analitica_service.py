"""Analítica/BI: tendencias mensuales, comparativas y proyección simple.

A diferencia de `dashboard_service` (un rango de fechas corto, pensado para
"¿cómo va hoy/este mes?"), este módulo mira varios MESES hacia atrás para
responder "¿hacia dónde va el negocio?" -- tendencia, mes-contra-mes, y una
proyección simple del próximo mes basada en la tendencia reciente.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, F, DecimalField
from django.db.models.functions import Coalesce, TruncMonth, ExtractWeekDay

from apps.facturacion.models import Factura, Detallefactura

MESES_TENDENCIA_DEFAULT = 12
MESES_TOP_PRODUCTOS_DEFAULT = 3
NOMBRES_MES = [
    'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
]
# Django `ExtractWeekday` es 1=domingo..7=sábado (convención de Postgres) --
# se remapea a un orden lunes-a-domingo, más natural para mostrar en el UI.
NOMBRES_DIA_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def _primer_dia_mes(anchor: date, meses_atras: int) -> date:
    mes_total = anchor.month - 1 - meses_atras
    anio = anchor.year + mes_total // 12
    mes = mes_total % 12 + 1
    return date(anio, mes, 1)


def obtener_tendencia_mensual(meses: int = MESES_TENDENCIA_DEFAULT) -> list[dict]:
    """Total vendido y número de facturas por mes, de los últimos `meses` (incluye el actual)."""
    hoy = date.today()
    desde = _primer_dia_mes(hoy, meses - 1)

    filas = (
        Factura.objects.filter(fecha_operacion__date__gte=desde)
        .exclude(estado__iexact='cancelada')
        .annotate(mes=TruncMonth('fecha_operacion'))
        .values('mes')
        .annotate(
            total=Coalesce(Sum('total_base'), Decimal('0.0')),
            num_facturas=Count('id'),
        )
        .order_by('mes')
    )
    por_mes = {f['mes'].date().replace(day=1): f for f in filas}

    resultado = []
    for i in range(meses - 1, -1, -1):
        mes_inicio = _primer_dia_mes(hoy, i)
        entrada = por_mes.get(mes_inicio)
        resultado.append({
            'anio': mes_inicio.year,
            'mes': mes_inicio.month,
            'label': f"{NOMBRES_MES[mes_inicio.month - 1]} {mes_inicio.year % 100:02d}",
            'total': float(entrada['total']) if entrada else 0.0,
            'num_facturas': entrada['num_facturas'] if entrada else 0,
        })
    return resultado


def obtener_comparativa_mensual(tendencia: list[dict] | None = None) -> dict:
    """Mes actual (a la fecha de hoy) contra el mismo tramo de días del mes anterior."""
    hoy = date.today()
    inicio_mes_actual = hoy.replace(day=1)
    inicio_mes_anterior = _primer_dia_mes(hoy, 1)
    # Mismo número de días transcurridos en ambos meses -- comparar "todo
    # septiembre" contra "lo que va de octubre" favorecería siempre al mes
    # ya cerrado, sin decir nada real sobre el ritmo actual.
    dias_transcurridos = (hoy - inicio_mes_actual).days

    def _total_rango(desde: date, dias: int) -> Decimal:
        hasta = desde + timedelta(days=dias)
        return Factura.objects.filter(
            fecha_operacion__date__gte=desde, fecha_operacion__date__lte=hasta,
        ).exclude(estado__iexact='cancelada').aggregate(
            total=Coalesce(Sum('total_base'), Decimal('0.0')),
        )['total']

    total_actual = _total_rango(inicio_mes_actual, dias_transcurridos)
    total_anterior_comparable = _total_rango(inicio_mes_anterior, dias_transcurridos)

    if total_anterior_comparable > 0:
        variacion_pct = float((total_actual - total_anterior_comparable) / total_anterior_comparable * 100)
    elif total_actual > 0:
        variacion_pct = None
    else:
        variacion_pct = None

    return {
        'total_mes_actual': float(total_actual),
        'total_mes_anterior_mismo_tramo': float(total_anterior_comparable),
        'dias_comparados': dias_transcurridos + 1,
        'variacion_pct': variacion_pct,
    }


def obtener_proyeccion_proximo_mes(tendencia: list[dict]) -> dict | None:
    """
    Regresión lineal simple (mínimos cuadrados) sobre el total mensual de
    los últimos meses, para estimar el mes siguiente -- no requiere numpy,
    la fórmula cerrada de una recta con un solo predictor (el índice del
    mes) es trivial de calcular a mano.

    Se ignora el mes actual (todavía incompleto) para no sesgar la recta
    hacia abajo solo porque el mes en curso no ha terminado.
    """
    meses_cerrados = tendencia[:-1] if len(tendencia) > 1 else tendencia
    # Un producto/negocio nuevo con menos de 3 meses de historial no da una
    # tendencia confiable -- se prefiere no proyectar nada a inventar una
    # recta con un solo punto.
    if len(meses_cerrados) < 3:
        return None

    xs = list(range(len(meses_cerrados)))
    ys = [m['total'] for m in meses_cerrados]
    n = len(xs)
    media_x = sum(xs) / n
    media_y = sum(ys) / n
    numerador = sum((x - media_x) * (y - media_y) for x, y in zip(xs, ys))
    denominador = sum((x - media_x) ** 2 for x in xs)
    if denominador == 0:
        pendiente = 0.0
    else:
        pendiente = numerador / denominador
    intercepto = media_y - pendiente * media_x

    siguiente_x = n
    proyeccion = intercepto + pendiente * siguiente_x
    # Una proyección negativa no tiene sentido para un total de ventas.
    proyeccion = max(proyeccion, 0.0)

    hoy = date.today()
    mes_siguiente = _primer_dia_mes(hoy, -1)

    return {
        'anio': mes_siguiente.year,
        'mes': mes_siguiente.month,
        'label': f"{NOMBRES_MES[mes_siguiente.month - 1]} {mes_siguiente.year % 100:02d}",
        'total_estimado': round(proyeccion, 2),
        'tendencia': 'creciente' if pendiente > 0.01 else ('decreciente' if pendiente < -0.01 else 'estable'),
    }


def obtener_top_productos_periodo(meses: int = MESES_TOP_PRODUCTOS_DEFAULT, limite: int = 10) -> list[dict]:
    hoy = date.today()
    desde = _primer_dia_mes(hoy, meses - 1)
    ventas_qs = Factura.objects.filter(fecha_operacion__date__gte=desde).exclude(estado__iexact='cancelada')

    return list(
        Detallefactura.objects.filter(factura__in=ventas_qs)
        .values('producto__nombre', 'variante__nombre')
        .annotate(
            cantidad_total=Coalesce(Sum('cantidad'), 0),
            ingresos_total=Coalesce(
                Sum(F('cantidad') * F('precio_unitario'), output_field=DecimalField()),
                Decimal('0.0'),
            ),
        )
        .order_by('-ingresos_total')[:limite]
    )


def obtener_ventas_por_dia_semana(meses: int = MESES_TOP_PRODUCTOS_DEFAULT) -> list[dict]:
    """Qué día de la semana vende más, en promedio -- útil para planear turnos/promos."""
    hoy = date.today()
    desde = _primer_dia_mes(hoy, meses - 1)
    filas = (
        Factura.objects.filter(fecha_operacion__date__gte=desde)
        .exclude(estado__iexact='cancelada')
        .annotate(dia_semana=ExtractWeekDay('fecha_operacion'))
        .values('dia_semana')
        .annotate(total=Coalesce(Sum('total_base'), Decimal('0.0')), num_facturas=Count('id'))
    )
    # ExtractWeekday: 1=domingo..7=sábado -- se remapea a índice 0=lunes..6=domingo.
    por_dia = {f['dia_semana']: f for f in filas}
    resultado = []
    for idx_lunes_domingo in range(7):
        dia_semana_django = 2 + idx_lunes_domingo if idx_lunes_domingo < 6 else 1
        entrada = por_dia.get(dia_semana_django)
        resultado.append({
            'dia': NOMBRES_DIA_SEMANA[idx_lunes_domingo],
            'total': float(entrada['total']) if entrada else 0.0,
            'num_facturas': entrada['num_facturas'] if entrada else 0,
        })
    return resultado


def obtener_analitica_completa(meses: int = MESES_TENDENCIA_DEFAULT) -> dict:
    tendencia = obtener_tendencia_mensual(meses)
    return {
        'tendencia_mensual': tendencia,
        'comparativa_mensual': obtener_comparativa_mensual(tendencia),
        'proyeccion_proximo_mes': obtener_proyeccion_proximo_mes(tendencia),
        'top_productos': obtener_top_productos_periodo(),
        'ventas_por_dia_semana': obtener_ventas_por_dia_semana(),
    }
