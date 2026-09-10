"""
Renderer por defecto que envuelve todas las respuestas JSON de la API
en el estándar ``{data, meta, errors}``.

Respeta el atributo ``erp_raw_response`` (definido en ``apps.core.response``)
para no volver a envolver respuestas ya formateadas, y deja pasar sin
modificar las respuestas binarias (PDF, imágenes) y el HTML de la API
browsable de DRF.
"""
from __future__ import annotations

from typing import Any, Dict

from rest_framework.renderers import JSONRenderer
from rest_framework.utils.encoders import JSONEncoder
from django.http.response import HttpResponseBase


class StandardJSONRenderer(JSONRenderer):
    """
    Envuelve el payload de cualquier respuesta JSON en:
    ``{"data": ..., "meta": {}, "errors": null}``.

    No envuelve:
        * Respuestas que ya contienen el marcador ``erp_raw_response``.
        * Respuestas binarias (el propio renderer de DRF las entrega porque
          no son instancias de dict/list serializables, típicamente PDF).
        * Respuestas cuyo payload ya sea la estructura estándar.
    """

    media_type = "application/json"
    format = "json"

    def render(
        self,
        data: Any,
        accepted_media_type: Any = None,
        renderer_context: Any = None,
    ) -> bytes:
        renderer_context = renderer_context or {}
        response: HttpResponseBase = renderer_context.get("response", None)

        # 1. No tocar respuestas ya estandarizadas.
        if response is not None and getattr(response, "erp_raw_response", False):
            return super().render(data, accepted_media_type, renderer_context)

        # 2. No tocar respuestas que no sean JSON serializables (PDF, etc.).
        if not isinstance(data, (dict, list, str, int, float, bool)) or data is None:
            return super().render(data, accepted_media_type, renderer_context)

        # 3. No volver a envolver si ya tiene la forma estándar.
        if isinstance(data, dict) and set(data.keys()) == {"data", "meta", "errors"}:
            return super().render(data, accepted_media_type, renderer_context)

        # 4. Envolver en la estructura estándar.
        wrapped: Dict[str, Any] = {
            "data": data,
            "meta": {},
            "errors": None,
        }
        return super().render(wrapped, accepted_media_type, renderer_context)
