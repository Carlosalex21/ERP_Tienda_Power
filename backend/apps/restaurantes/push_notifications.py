"""
Web Push para el staff -- avisa "llaman al mesero"/"piden la cuenta" aunque
la pestaña del panel no esté enfocada o el teléfono tenga la pantalla
apagada (el WebSocket de `apps.restaurantes.consumers` solo entrega mientras
la conexión sigue viva). Se envía a TODAS las suscripciones del tenant activo
-- cualquier mesero puede atender cualquier mesa, no hay "dueño" por pedido.

Fail-open, como el resto de los side-effects "avisar en vivo" de este
módulo: nunca debe poder tumbar la vista que llama a esto. Una suscripción
vencida/inválida (el navegador la revocó, el usuario desinstaló la PWA) se
borra en silencio -- eso es justamente lo que el error 404/410 del servicio
de push significa.
"""
from __future__ import annotations

import base64
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _vapid_pem() -> str | None:
    if not settings.VAPID_PRIVATE_KEY_PEM_B64:
        return None
    try:
        return base64.b64decode(settings.VAPID_PRIVATE_KEY_PEM_B64).decode()
    except Exception:
        logger.warning('VAPID_PRIVATE_KEY_PEM_B64 configurada pero no se pudo decodificar.', exc_info=True)
        return None


def enviar_push_a_staff(titulo: str, cuerpo: str, url: str | None = None) -> None:
    """
    `url` (opcional): a qué pantalla del panel llevar al hacer clic en la
    notificación (ver `notificationclick` en `public/sw.js`) -- sin
    especificarla, cae en el comportamiento histórico (abrir/enfocar
    `/admin/restaurante/mesas`). Esta función es genérica a propósito (no
    depende de nada de `Mesa`/`PedidoMesa`): cualquier app del sistema
    (postventa, reportes, etc.) la importa igual para avisar algo urgente
    al staff, sin duplicar la lógica de Web Push.
    """
    if not settings.VAPID_PRIVATE_KEY_PEM_B64:
        return  # Web Push no configurado en este tenant/entorno -- se omite en silencio.

    try:
        from pywebpush import webpush, WebPushException
        from .models import PushSubscription

        pem = _vapid_pem()
        if not pem:
            return

        payload = json.dumps({"title": titulo, "body": cuerpo, "url": url})
        vapid_claims = {"sub": settings.VAPID_SUBJECT}

        for sub in PushSubscription.objects.all():
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=pem,
                    vapid_claims=dict(vapid_claims),
                )
            except WebPushException as exc:
                # 404/410 = el navegador invalidó esta suscripción (usuario
                # revocó el permiso, la reinstaló, etc.) -- se borra para no
                # seguir intentando en vano en cada aviso futuro.
                status_code = getattr(exc.response, 'status_code', None)
                if status_code in (404, 410):
                    sub.delete()
                else:
                    logger.warning('Error enviando push a %s', sub.endpoint, exc_info=True)
    except Exception:
        logger.warning('No se pudo enviar la notificación push al staff', exc_info=True)
