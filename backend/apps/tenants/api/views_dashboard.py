from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from datetime import timedelta
from django.db import connection
from drf_spectacular.utils import extend_schema
from .serializers import PlatformDashboardSerializer

try:
    import psutil
    PSUTIL_INSTALLED = True
except ImportError:
    PSUTIL_INSTALLED = False

from apps.tenants.models import Client, Subscription

class PlatformDashboardView(APIView):
    """
    Proporciona métricas clave para el administrador de la plataforma.
    """
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Obtener Métricas del Dashboard de la Plataforma",
        responses=PlatformDashboardSerializer
    )
    def get(self, request):
        # Métricas de negocio
        active_subscriptions = Subscription.objects.filter(estado='activa', fecha_fin__gte=timezone.now())
        monthly_recurring_revenue = sum(sub.plan.precio for sub in active_subscriptions)
        
        thirty_days_ago = timezone.now() - timedelta(days=30)
        new_clients_last_30_days = Client.objects.filter(fecha_creacion__gte=thirty_days_ago.date()).count()

        # Métricas de salud del sistema
        system_health = {
            "cpu_usage_percent": psutil.cpu_percent(interval=1) if PSUTIL_INSTALLED else None,
            "memory_usage_percent": psutil.virtual_memory().percent if PSUTIL_INSTALLED else None,
            "disk_usage_percent": psutil.disk_usage('/').percent if PSUTIL_INSTALLED else None,
        }

        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active';")
            active_db_connections = cursor.fetchone()[0]
            cursor.execute("SHOW max_connections;")
            max_db_connections = int(cursor.fetchone()[0])

        data = {
            "business_metrics": {
                "active_tenants": Client.objects.filter(esta_activo=True).count(),
                "active_subscriptions": active_subscriptions.count(),
                "monthly_recurring_revenue": f"{monthly_recurring_revenue:.2f}",
                "new_clients_last_30_days": new_clients_last_30_days,
            },
            "system_health": system_health,
            "db_health": {
                "active_connections": active_db_connections,
                "max_connections": max_db_connections,
                "usage_percent": round((active_db_connections / max_db_connections) * 100, 2) if max_db_connections > 0 else 0,
            }
        }
        return Response(data)