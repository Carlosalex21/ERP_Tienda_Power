"""
Exception handler global de DRF.

Sin esto, un error de validación (400) devuelve el dict nativo de DRF
(``{"campo": ["mensaje"]}``) tal cual, y el ``StandardJSONRenderer`` lo
envuelve sin distinguir éxito de error -- queda como
``{"data": {"campo": [...]}, "errors": null}``. El frontend
(``getApiErrorMessages``) solo sabe leer errores desde ``errors``, así que
terminaba mostrando siempre un mensaje genérico ("Error al guardar...")
en vez del motivo real devuelto por el backend.

Este handler intercepta la excepción ANTES del renderer y construye la
respuesta ya en el formato estándar (``error_response_from_dict``), que se
marca como ``erp_raw_response`` y por lo tanto el renderer la deja pasar
sin volver a envolverla.
"""
from __future__ import annotations

from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.response import error_response_from_dict


def custom_exception_handler(exc, context):
    """Normaliza cualquier error de DRF al formato ``{data, meta, errors}``."""
    response = drf_exception_handler(exc, context)

    if response is None:
        # Excepción no manejada por DRF (bug real): la dejamos subir para
        # que Django la loguee/reporte normalmente en vez de ocultarla.
        return None

    return error_response_from_dict(response.data, status_code=response.status_code)
