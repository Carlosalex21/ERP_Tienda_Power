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


# Claves que DRF/las vistas usan para un error "general" (no atado a un campo
# del formulario): `{"detail": ...}`, `{"error": ...}`, `non_field_errors`...
_CLAVES_GLOBALES = frozenset({"detail", "error", "errors", "mensaje", "message", "non_field_errors"})


def _aplanar_errores(valor: Any, campo: Optional[str], salida: List[Dict[str, Any]]) -> None:
    """
    Recorre cualquier estructura de errores de DRF y la deja plana.

    Un serializer con líneas anidadas (ej. ``detalles_para_crear``) devuelve
    ``{"detalles_para_crear": [{}, {"cantidad": ["..."]}]}``: antes cada
    dict interno se convertía con ``str()`` y el usuario veía basura tipo
    ``{'cantidad': [ErrorDetail(...)]}``. Ahora el campo es la ruta
    (``detalles_para_crear.1.cantidad``) y el mensaje es solo el texto.
    """
    if isinstance(valor, dict):
        for clave, sub in valor.items():
            clave = str(clave)
            if campo is None and clave in _CLAVES_GLOBALES:
                ruta = None
                codigo = clave
            else:
                ruta = clave if campo is None else f"{campo}.{clave}"
                codigo = clave
            if isinstance(sub, (dict, list, tuple)):
                _aplanar_errores(sub, ruta, salida)
            else:
                salida.append({"code": codigo, "detail": str(sub), "field": ruta})
    elif isinstance(valor, (list, tuple)):
        for indice, item in enumerate(valor):
            if isinstance(item, dict) and set(item.keys()) >= {"detail"} and campo is None:
                salida.append({
                    "code": item.get("code", "error"),
                    "detail": str(item.get("detail", "")),
                    "field": item.get("field"),
                })
            elif isinstance(item, (dict, list, tuple)):
                if item:  # los dicts vacíos son líneas válidas dentro de una lista con errores
                    _aplanar_errores(item, f"{campo}.{indice}" if campo else None, salida)
            else:
                salida.append({"code": campo or "error", "detail": str(item), "field": campo})
    else:
        salida.append({"code": "error", "detail": str(valor), "field": campo})


def errores_desde_payload(payload: Any) -> List[Dict[str, Any]]:
    """Lista estándar ``[{code, detail, field}]`` a partir de cualquier payload de error."""
    errores: List[Dict[str, Any]] = []
    _aplanar_errores(payload, None, errores)
    return [e for e in errores if e["detail"]]


def error_response_from_dict(
    error_dict: Any,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """
    Convierte el payload de error de DRF (o de una vista que devolvió
    ``Response({"error": "..."}, status=400)``) en el formato estandarizado.
    """
    errores = errores_desde_payload(error_dict) or [
        {"code": "error", "detail": "No se pudo completar la operación.", "field": None}
    ]
    return error_response(errores, status_code=status_code)


class StandardResultsSetPagination(PageNumberPagination):
    """
    Paginación estándar con envoltura ``meta.pagination``.

    Dos modos, según lo que pida el cliente:

    - **Paginado** (si viene ``?page=`` o ``?page_size=``): páginas de
      ``page_size`` (20 por defecto, máx. 200). Es lo que usan las tablas
      grandes con paginación del lado del servidor.
    - **Lista completa** (sin ninguno de los dos): devuelve TODOS los
      registros hasta ``LISTA_COMPLETA_MAX``. Antes se cortaba en 20 sin
      avisar, y como casi todo el frontend (POS, selectores, listados) pide
      el endpoint "a secas" y espera la lista entera, un negocio con más de
      20 productos/proveedores/clientes veía la lista recortada. Si el total
      supera el tope, ``meta.pagination.truncated`` lo indica.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200
    LISTA_COMPLETA_MAX = 5000

    _lista_completa = False

    def paginate_queryset(self, queryset, request, view=None):
        parametros = request.query_params
        self._lista_completa = "page" not in parametros and "page_size" not in parametros
        if not self._lista_completa:
            return super().paginate_queryset(queryset, request, view)

        self.request = request
        paginador = self.django_paginator_class(queryset, self.LISTA_COMPLETA_MAX)
        self.page = paginador.page(1)
        return list(self.page)

    def get_page_size(self, request):
        if self._lista_completa:
            return self.LISTA_COMPLETA_MAX
        return super().get_page_size(request)

    def get_paginated_response(self, data: Any) -> Response:
        """Construye la respuesta paginada estandarizada."""
        total = self.page.paginator.count
        meta = {
            "pagination": {
                "count": total,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "total_pages": self.page.paginator.num_pages,
                "truncated": bool(self._lista_completa and total > self.LISTA_COMPLETA_MAX),
            }
        }
        return standard_response(data=data, meta=meta)
