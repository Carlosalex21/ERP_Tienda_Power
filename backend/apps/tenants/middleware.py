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
RUTAS_EXENTAS = (
    '/api/v1/auth/',
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
