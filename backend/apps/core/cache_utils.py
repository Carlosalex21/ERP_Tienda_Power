"""
Utilidades de caché con Redis.

Centralizan las claves de caché, los TTLs y el patrón ``cache/decorator`` para
reducir la carga sobre PostgreSQL en peticiones recurrentes (catálogos,
configuraciones globales, parámetros fiscales).

Las claves se aíslan por tenant (``schema_name``) para evitar fugas de datos
entre inquilinos cuando se usa un Redis compartido. Las claves son legibles
(``<tenant>:<part1>:<part2>:...``) para poder invalidar por patrón con
``SCAN``/``delete_pattern``.
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Optional, TypeVar


from django.conf import settings
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Nombre de la clave redis subyacente que usa el backend de Django.
_KEY_PREFIX = getattr(settings, "CACHES", {}).get("default", {}).get("KEY_PREFIX", "erp_saas")


def _tenant_prefix() -> str:
    """Devuelve el prefijo del tenant actual para aislar las claves de caché."""
    try:
        schema_name = getattr(connection, "schema_name", None)
        if schema_name:
            return schema_name
    except Exception:  # noqa: BLE001 - Cualquier fallo debe caer a 'public'
        pass
    return "public"


def cache_key(*parts: str) -> str:
    """
    Construye una clave de caché única, versionada por tenant.

    El formato es ``<KEY_PREFIX>:<tenant>:<part1>:<part2>:...``. Al ser
    legible, permite invalidar por patrón con Redis SCAN/glob.
    """
    prefix = _tenant_prefix()
    clean_parts = [str(p).strip(":") for p in parts if p is not None]
    raw = ":".join([_KEY_PREFIX, prefix, *clean_parts])
    return raw


def get_cached(key: str) -> Any:
    """Lee un valor desde la caché. Devuelve None si no existe o hay error."""
    try:
        return cache.get(key)
    except Exception as exc:  # noqa: BLE001 - Redis caído no debe romper la API
        logger.warning("Error al leer caché '%s': %s", key, exc)
        return None


def set_cached(key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Guarda un valor en caché con un TTL opcional."""
    if ttl is None:
        ttl = getattr(settings, "CACHE_TTL", {}).get("configuraciones", 600)
    try:
        cache.set(key, value, timeout=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error al escribir caché '%s': %s", key, exc)


def invalidate(key: str) -> None:
    """Invalida una clave concreta."""
    try:
        cache.delete(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error al invalidar caché '%s': %s", key, exc)


def _redis_scan_delete(pattern: str) -> bool:
    """
    Intenta borrar claves con ``SCAN`` usando el cliente Redis subyacente.

    Devuelve True si se pudo ejecutar (independientemente de cuántas claves
    borró). Esto cubre backends de Django y django-redis sin depender de
    ``delete_pattern``.
    """
    try:
        backend = cache
        client = None
        # django.core.cache.backends.redis.RedisCache expone `.client`.
        if hasattr(backend, "client"):
            redis_client = backend.client
            # El cliente puede ser un wrapper; obtener el cliente raw.
            if hasattr(redis_client, "get_client"):
                client = redis_client.get_client(write=True)
            elif hasattr(redis_client, "connection_pool"):
                client = redis_client
        # django-redis: `cache.client.get_client()` o `cache.connection_factory`.
        if client is None and hasattr(backend, "connection_factory"):
            client = backend.connection_factory.get_connection()
        if client is None:
            return False

        # Completar el patrón para que coincida con el prefijo de claves.
        full_pattern = f"{_KEY_PREFIX}:*" if pattern == "*" else f"{_KEY_PREFIX}:{pattern}*"

        cursor = 0
        deleted = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match=full_pattern, count=200)
            if keys:
                client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        if deleted:
            logger.debug("SCAN eliminó %d claves con patrón '%s'.", deleted, pattern)
        return True
    except NotImplementedError:  # noqa: BLE001
        logger.debug("El backend de caché no soporta SCAN")
        return False
    except Exception as exc:  # noqa: BLE001 - Redis caído no debe romper la API
        logger.warning("Error al invalidar patrón '%s' con SCAN: %s", pattern, exc)
        return False


def invalidate_pattern(pattern: str) -> None:
    """
    Invalida todas las claves que coincidan con el patrón.

    Nota: en Redis esto se implementa con ``SCAN`` para no bloquear el server.
    Si el backend no soporta borrado por patrón, intenta con ``delete`` simple
    y degrada con una advertencia (sin romper la petición).
    """
    try:
        # django-redis soporta delete_pattern directamente.
        cache.delete_pattern(f"{_KEY_PREFIX}:{pattern}*")  # type: ignore[attr-defined]
        return
    except NotImplementedError:  # noqa: BLE001
        pass
    except Exception:  # noqa: BLE001 - Atributo inexistente u otro backend
        pass

    # Fallback con SCAN para backends estándar de Django.
    if _redis_scan_delete(pattern):
        return

    # Último recurso: borrar la clave exacta (sin sufijos).
    try:
        cache.delete(pattern)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo invalidar '%s': %s", pattern, exc)


def _default_key_builder(func: Callable[..., Any], args: tuple, kwargs: dict) -> tuple:
    """Construye la clave por defecto a partir de la firma de la función."""
    parts = [func.__module__, func.__qualname__]
    for arg in args:
        parts.append(str(arg))
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}={v}")
    return tuple(parts)


def cached(ttl: Optional[int] = None, key_builder: Optional[Callable[..., Any]] = None):
    """
    Decorador que cachea el resultado de una función.

    Args:
        ttl: Tiempo de vida en segundos. Si es None usa ``settings.CACHE_TTL``.
        key_builder: Función que construye la clave a partir de los args/kwargs.

    La clave de caché se aísla automáticamente por tenant. Si Redis está caído,
    la función se ejecuta normalmente (fallback a la base de datos).
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if key_builder is not None:
                parts = key_builder(*args, **kwargs)
                if isinstance(parts, str):
                    key = cache_key(parts)
                else:
                    key = cache_key(*parts)
            else:
                key = cache_key(*_default_key_builder(func, args, kwargs))

            cached_value = get_cached(key)
            if cached_value is not None:
                return cached_value

            result = func(*args, **kwargs)
            set_cached(key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
