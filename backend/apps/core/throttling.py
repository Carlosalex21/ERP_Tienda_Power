"""
Throttles resilientes: no deben tumbar la API si Redis está caído.

``SimpleRateThrottle.allow_request`` (DRF) llama directamente a
``self.cache.get()``/``self.cache.set()`` sin manejar errores. Mientras
``CACHES['default']`` fue ``LocMemCache`` (memoria de proceso, nunca falla al
conectar) esto nunca se notó. Al conectar el backend Redis real -- para que
la caché de catálogo/configuración por fin sea compartida entre workers --
un Redis caído empezó a tumbar con un 500 *cualquier* vista con throttle:
login, catálogo público, etc.

Estas subclases degradan a "permitir la request" si el caché no responde,
igual que ya hace ``apps.core.cache_utils`` para el resto de la app -- un
throttle que falla abierto es preferible a una API caída.
"""
from __future__ import annotations

import logging

from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)


class _ResilientThrottleMixin:
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception as exc:  # noqa: BLE001 - un caché caído no debe tumbar la API
            logger.warning("Throttle degradado (caché no disponible): %s", exc)
            return True


class ResilientAnonRateThrottle(_ResilientThrottleMixin, AnonRateThrottle):
    pass


class ResilientUserRateThrottle(_ResilientThrottleMixin, UserRateThrottle):
    pass


class ResilientScopedRateThrottle(_ResilientThrottleMixin, ScopedRateThrottle):
    pass
