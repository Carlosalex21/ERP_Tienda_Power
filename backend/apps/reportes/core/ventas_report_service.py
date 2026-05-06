from datetime import datetime, time
from django.utils import timezone
from apps.facturacion.models import Factura

def obtener_cierre_caja_service(date_str=None):
    """
    Calcula el total ingresado en caja y devuelve las transacciones
    para un día específico.
    """
    # 1. Definir la fecha objetivo
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        target_date = timezone.localdate()

    # 2. Crear rango de 24 horas consciente de la zona horaria
    start_of_day = timezone.make_aware(datetime.combine(target_date, time.min))
    end_of_day = timezone.make_aware(datetime.combine(target_date, time.max))

    # 3. Filtrar las facturas pagadas en ese rango
    facturas = Factura.objects.filter(
        fecha_operacion__range=(start_of_day, end_of_day),
        estado__iexact='pagado'
    ).select_related('cliente', 'usuario', 'metodo_pago').order_by('fecha_operacion')

    # 4. Calcular el total
    total_caja = sum(f.total for f in facturas)

    return target_date, total_caja, facturas


def obtener_reporte_ventas_service(start_date_str, end_date_str, estado=None, cliente_id=None):
    """
    Genera un queryset filtrado para reportes históricos de ventas 
    (con o sin detalles).
    """
    if not start_date_str or not end_date_str:
        raise ValueError("Se requieren start_date y end_date con formato YYYY-MM-DD.")

    # 1. Parsear fechas
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    # 2. Crear rango de horas
    start_of_day = timezone.make_aware(datetime.combine(start_date, time.min))
    end_of_day = timezone.make_aware(datetime.combine(end_date, time.max))

    # 3. Queryset base ultra-optimizado
    queryset = Factura.objects.filter(
        fecha_operacion__range=(start_of_day, end_of_day)
    ).select_related(
        'cliente', 'usuario', 'metodo_pago'
    ).prefetch_related(
        'detalles', 'detalles__producto', 'detalles__variante'
    ).order_by('-fecha_operacion')

    # 4. Aplicar filtros opcionales
    if estado:
        queryset = queryset.filter(estado__iexact=estado)
    if cliente_id:
        queryset = queryset.filter(cliente_id=cliente_id)

    return queryset