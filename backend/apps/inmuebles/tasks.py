"""
Tarea diaria de cobranza para los tenants de condominios e inmobiliaria:

1. Vence los contratos terminados y genera los cánones del mes de los vigentes.
2. Aplica la mora del mes a las deudas vencidas (una vez por deuda y por mes).

Es idempotente: correrla dos veces el mismo día no duplica nada.
"""
import logging

from celery import shared_task
from django_tenants.utils import tenant_context

logger = logging.getLogger(__name__)

TIPOS_INMUEBLES = ('condominios', 'inmobiliaria')


@shared_task
def procesar_cobranza_diaria():
    from apps.tenants.models import Client

    for tenant in Client.objects.filter(tipo_negocio__in=TIPOS_INMUEBLES).exclude(schema_name='public'):
        try:
            with tenant_context(tenant):
                from apps.inmuebles.services import cobranza, contratos

                resumen = contratos.procesar_contratos()
                moras = cobranza.aplicar_mora()
                logger.info('Cobranza %s: %s, moras=%s', tenant.schema_name, resumen, moras)
        except Exception:
            logger.warning('No se pudo procesar la cobranza del tenant %s', tenant.schema_name, exc_info=True)
