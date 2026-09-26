"""
Bloquea el acceso al panel de un tenant cuando su suscripción venció (y ya
pasó el período de gracia configurado) -- antes NADA impedía seguir usando
el sistema indefinidamente sin pagar, ni antes ni después de que expirara
el plan de prueba.

Se inserta justo después de `TenantMainMiddleware` (necesita `request.tenant`
ya resuelto) y solo actúa quien esté en el esquema de un tenant real -- el
esquema público (registro, pago de suscripción, panel de superadmin) nunca
se bloquea por esto.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.http import JsonResponse
from django_tenants.utils import get_public_schema_name

# Prefijos de ruta que SIEMPRE pasan, incluso con la suscripción vencida:
# el dueño necesita poder autenticarse y ver su propio estado de cuenta
# para poder ir a pagar y reactivar su tenant.
#
# OJO: antes esto era el prefijo genérico `/api/v1/auth/` completo -- como
# `apps.usuarios.urls` también cuelga de ahí la gestión de EMPLEADOS y
# ROLES (`/api/v1/auth/management/`, `/api/v1/auth/roles/`), un tenant con
# la suscripción vencida podía seguir administrando su plantilla sin pagar.
# Se listan explícitas solo las rutas que en verdad necesita alguien
# bloqueado para poder pagar y reactivarse.
RUTAS_EXENTAS = (
    '/api/v1/auth/token/',
    '/api/v1/auth/me/',
    '/api/v1/auth/password-reset/',
    '/api/v1/tenants/profile/',
    '/admin/',
)


class SubscriptionGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != 'OPTIONS' and self._debe_bloquear(request):
            return JsonResponse(
                {
                    "error": "suscripcion_vencida",
                    "detail": "La suscripción de este negocio venció. Renueva el plan para seguir usando el sistema.",
                },
                status=402,
            )
        return self.get_response(request)

    @staticmethod
    def _debe_bloquear(request) -> bool:
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant.schema_name == get_public_schema_name():
            return False

        path = request.path
        if any(path.startswith(prefix) for prefix in RUTAS_EXENTAS):
            return False

        sub = getattr(tenant, 'subscription', None)
        if sub is None or sub.is_active:
            return False

        # Período de gracia tras el vencimiento (configurable por el superadmin).
        from apps.tenants.services import platform_settings_service

        dias_gracia = platform_settings_service.obtener_configuracion().dias_gracia_tras_vencimiento
        if sub.fecha_fin is None:
            return True
        limite = sub.fecha_fin + timedelta(days=dias_gracia)
        # `date.today()`, no `timezone.now().date()` -- `fecha_fin`/`limite`
        # se derivan de un `DateField` grabado con la fecha del SO (ver
        # `apps.tenants.models.Subscription.is_active`); comparar contra la
        # fecha de `timezone.now()` puede bloquear un día antes de tiempo.
        return date.today() > limite


class PlanModulosMiddleware:
    """
    Bloquea (403) los endpoints de un módulo que el plan del tenant no
    incluye -- sin esto, ocultar el módulo en el panel no impedía usarlo
    llamando a la API directamente. Solo actúa sobre las rutas exclusivas de
    cada módulo (ver `apps.tenants.modulos`); va después de
    `SubscriptionGateMiddleware`, que ya resolvió `request.tenant`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        codigo = None if request.method == 'OPTIONS' else self._modulo_bloqueado(request)
        if codigo:
            return JsonResponse(
                {
                    "error": "modulo_no_incluido",
                    "modulo": codigo,
                    "detail": "Este módulo no está incluido en tu plan. Mejora tu plan para usarlo.",
                },
                status=403,
            )
        return self.get_response(request)

    @staticmethod
    def _modulo_bloqueado(request) -> str | None:
        from apps.tenants.modulos import modulo_de_ruta

        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant.schema_name == get_public_schema_name():
            return None
        codigo = modulo_de_ruta(request.path)
        if codigo is None:
            return None
        sub = getattr(tenant, 'subscription', None)
        plan = getattr(sub, 'plan', None) if sub is not None else None
        if plan is None or plan.incluye_modulo(codigo):
            return None
        return codigo
