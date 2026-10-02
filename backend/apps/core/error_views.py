"""
Manejadores globales de 404/500 para la API.

Django, ante una URL inexistente o un error no controlado, devuelve una
página HTML. El frontend espera siempre la envoltura ``{data, meta, errors}``:
con HTML no podía mostrar nada útil. Para rutas ``/api/`` se responde JSON
estándar con un mensaje comprensible; el resto de rutas conserva el
comportamiento por defecto de Django.
"""
from __future__ import annotations

import logging

from django.http import JsonResponse
from django.views import defaults

logger = logging.getLogger("erp.errores")


def _json_error(status: int, code: str, detail: str) -> JsonResponse:
    return JsonResponse(
        {"data": None, "meta": {}, "errors": [{"code": code, "detail": detail, "field": None}]},
        status=status,
    )


def not_found(request, exception=None):
    if request.path.startswith("/api/"):
        return _json_error(404, "not_found", "No encontramos lo que buscas.")
    return defaults.page_not_found(request, exception)


def server_error(request):
    # Un 500 es un bug real: se registra con el traceback para poder
    # diagnosticarlo (y para que Sentry lo capture cuando se configure).
    logger.error("Error 500 en %s %s", request.method, request.path, exc_info=True)
    if request.path.startswith("/api/"):
        return _json_error(
            500, "server_error",
            "Algo salió mal de nuestro lado. Ya quedó registrado; inténtalo de nuevo en unos minutos.",
        )
    return defaults.server_error(request)
