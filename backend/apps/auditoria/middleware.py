"""
Contexto de "usuario actual" para las señales de auditoría.

Las señales `post_save`/`post_delete` (ver `signals.py`) no reciben el
`request` -- no tienen forma de saber QUIÉN hizo el cambio. Este middleware
guarda la petición en curso en una variable thread-local, que las señales
leen para firmar cada registro de auditoría.

IMPORTANTE: se guarda el `request` completo, no una copia de `request.user`
tomada al entrar al middleware. La API se autentica con JWT
(`rest_framework_simplejwt`), y DRF resuelve `request.user` de forma
perezosa DENTRO de la vista (la primera vez que algo lo lee, ej. un chequeo
de permisos) -- en el momento en que este middleware se ejecuta, `self.
get_response(request)` todavía no corrió, así que `request.user` en ese
instante es siempre `AnonymousUser` aunque la petición sí esté autenticada.
Guardando el objeto `request` y leyendo `.user` recién cuando una señal lo
pide (que ocurre DURANTE la vista, después de que DRF ya autenticó), se
obtiene el usuario real -- DRF sincroniza `request.user` de vuelta al
`HttpRequest` original en cuanto se accede una vez (ver `Request.user`
setter en `rest_framework/request.py`).
"""
from __future__ import annotations

import threading
from typing import Any

_local = threading.local()


def get_current_user() -> Any:
    request = getattr(_local, 'request', None)
    if request is None:
        return None
    return getattr(request, 'user', None)


def get_current_ip() -> str | None:
    return getattr(_local, 'ip', None)


def _client_ip(request) -> str | None:
    # Detrás de un proxy/load balancer, `REMOTE_ADDR` es la IP del proxy, no
    # la del cliente real -- por eso se prioriza X-Forwarded-For (el primer
    # valor de la lista es el cliente original).
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AuditoriaMiddleware:
    """Debe ir DESPUÉS de `AuthenticationMiddleware` en `MIDDLEWARE`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        _local.ip = _client_ip(request)
        try:
            return self.get_response(request)
        finally:
            # Limpia SIEMPRE, incluso si la vista lanzó una excepción --
            # de lo contrario, en un worker con threads reutilizados, la
            # siguiente petición (ej. una tarea sin usuario) podría heredar
            # por error el usuario de una petición anterior.
            _local.request = None
            _local.ip = None
