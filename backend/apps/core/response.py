"""
Estándar de respuesta JSON para toda la API del ERP.

Estructura única y predecible:
    {
        "data": <payload | null>,
        "meta": { "pagination": {...} | null, "tenant": "schema_name" | null },
        "errors": [ { "code": str, "detail": str, "field": str | null } ] | null
    }

Uso:
    from apps.core.response import standard_response, error_response

    return standard_response(data={"items": [...]}, meta={"pagination": {...}})
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

# Atributo usado por APIRenderer para no volver a envolver respuestas ya
# formateadas por el backend.
RAW_RESPONSE_ATTR = "erp_raw_response"


def standard_response(
    data: Any = None,
    meta: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
    status_code: int = status.HTTP_200_OK,
    http_status: Optional[int] = None,
) -> Response:
    """
    Construye una respuesta estandarizada ``{data, meta, errors}``.

    Args:
        data: Payload principal de la respuesta.
        meta: Metadatos adicionales (paginación, tenant, etc.).
        errors: Lista de errores normalizados.
        status_code: Código HTTP de la respuesta.
        http_status: Alias opcional de ``status_code`` (mantiene compatibilidad).

    Returns:
        Response: Respuesta DRF envuelta en el estándar.
    """
    code = http_status if http_status is not None else status_code
    payload = {
        "data": data,
        "meta": meta or {},
        "errors": errors or None,
    }
    response = Response(payload, status=code)
    setattr(response, RAW_RESPONSE_ATTR, True)
    return response


def error_response(
    errors: List[Dict[str, Any]],
    status_code: int = status.HTTP_400_BAD_REQUEST,
    http_status: Optional[int] = None,
) -> Response:
    """
    Respuesta estandarizada de error.

    Args:
        errors: Lista de diccionarios ``{code, detail, field}``.
        status_code: Código HTTP.
        http_status: Alias opcional de ``status_code``.

    Returns:
        Response: Respuesta de error estandarizada.
    """
    return standard_response(
        data=None, errors=errors,
        status_code=status_code, http_status=http_status,
    )


def error_response_from_dict(
    error_dict: Dict[str, Any],
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """
    Convierte un diccionario de errores de DRF en el formato estandarizado.

    Args:
        error_dict: Diccionario ``{campo: [mensajes]}`` o ``{detail: msg}``.
        status_code: Código HTTP de la respuesta.

    Returns:
        Response: Respuesta de error estandarizada.
    """
    errors: List[Dict[str, Any]] = []

    if isinstance(error_dict, dict):
        for field, value in error_dict.items():
            if isinstance(value, (list, tuple)):
                for item in value:
                    errors.append({
                        "code": field,
                        "detail": str(item),
                        "field": None if field == "detail" else str(field),
                    })
            else:
                errors.append({
                    "code": field,
                    "detail": str(value),
                    "field": None if field == "detail" else str(field),
                })
    elif isinstance(error_dict, (list, tuple)):
        for item in error_dict:
            if isinstance(item, dict):
                errors.append({
                    "code": item.get("code", "error"),
                    "detail": str(item.get("detail", "")),
                    "field": item.get("field"),
                })
            else:
                errors.append({
                    "code": "error",
                    "detail": str(item),
                    "field": None,
                })
    else:
        errors.append({
            "code": "error",
            "detail": str(error_dict),
            "field": None,
        })

    return error_response(errors, status_code=status_code)


class StandardResultsSetPagination(PageNumberPagination):
    """
    Paginación estándar que envuelve los resultados en ``meta.pagination``.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data: Any) -> Response:
        """Construye la respuesta paginada estandarizada."""
        meta = {
            "pagination": {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "total_pages": self.page.paginator.num_pages,
            }
        }
        return standard_response(data=data, meta=meta)
