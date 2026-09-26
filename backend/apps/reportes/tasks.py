"""
Tareas periódicas de Reportes -- por ahora, un solo "digest" diario de
alertas urgentes por Web Push (ver `CELERY_BEAT_SCHEDULE` en
`backend/settings.py`, que dispara `enviar_digest_alertas_urgentes` cada
hora).

Se ejecuta cada hora pero solo AVISA una vez por tenant por día (vía un
flag en el cache de Redis, con TTL de 20h) -- si se dejara sin este freno,
un tenant con una cuenta por cobrar vencida recibiría el mismo push cada
hora indefinidamente hasta que alguien la cobre, lo cual entrena al usuario
a ignorar la notificación en vez de prestarle atención.
"""
import logging

from celery import shared_task
from django.core.cache import cache
from django_tenants.utils import tenant_context

logger = logging.getLogger(__name__)

CLAVE_CACHE_DIGEST = 'alertas-digest-enviado:{schema}'
# 20h (no 24h): dejando un margen bajo el día completo, si el proceso de
# celery-beat se reinicia o se atrasa un poco, el aviso del día siguiente no
# corre riesgo de saltarse por completo esperando a que se cumplan las 24h
# exactas desde el aviso anterior.
TTL_DIGEST = 60 * 60 * 20


@shared_task
def enviar_digest_alertas_urgentes():
    from apps.tenants.models import Client

    for tenant in Client.objects.exclude(schema_name='public'):
        try:
            _procesar_tenant(tenant)
        except Exception:
            logger.warning('No se pudo procesar el digest de alertas para el tenant %s', tenant.schema_name, exc_info=True)


def _procesar_tenant(tenant) -> None:
    clave = CLAVE_CACHE_DIGEST.format(schema=tenant.schema_name)
    if cache.get(clave):
        return  # Ya se avisó a este tenant hoy.

    with tenant_context(tenant):
        from .core.alertas_service import obtener_alertas
        resultado = obtener_alertas()
        if resultado['urgentes'] <= 0:
            return  # Nada urgente -- no se marca el flag, se puede reintentar la próxima hora sin costo.

        from apps.restaurantes.push_notifications import enviar_push_a_staff
        plural = 's' if resultado['urgentes'] != 1 else ''
        enviar_push_a_staff(
            'Tienes alertas urgentes',
            f"{resultado['urgentes']} alerta{plural} urgente{plural} esperando en tu Centro de Alertas.",
            url='/admin/alertas',
        )

    cache.set(clave, True, TTL_DIGEST)
