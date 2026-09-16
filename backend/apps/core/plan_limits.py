"""
Límites de uso según el plan de suscripción contratado.

`Plan.limite_usuarios`/`limite_sucursales`/`limite_productos` existían (los
dos primeros desde el modelo original) pero nada los hacía cumplir -- un
tenant en el plan más barato podía crear tantos usuarios, sucursales o
productos como quisiera, exactamente igual que uno en el plan más caro. Esto
cierra esa brecha, aplicando justo lo que la página de precios promete
(ej. "Hasta 100 productos" en el plan Emprendedor).
"""
from __future__ import annotations

from rest_framework.exceptions import PermissionDenied


def obtener_plan_activo(request):
    """Plan de la suscripción activa del tenant actual, o `None` si no hay ninguna activa."""
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return None
    sub = getattr(tenant, "subscription", None)
    if sub is None or not sub.is_active:
        return None
    return sub.plan


def verificar_limite(request, campo_limite: str, conteo_actual: int, nombre_recurso: str) -> None:
    """
    Lanza `PermissionDenied` (403) si crear un recurso más superaría el
    límite del plan activo.

    Un límite ausente/`None`/0 en el plan, o ningún plan activo resoluble,
    significa "sin restricción" -- nunca bloqueamos por un dato que no
    pudimos determinar con certeza.
    """
    plan = obtener_plan_activo(request)
    if plan is None:
        return
    limite = getattr(plan, campo_limite, None)
    if not limite:
        return
    if conteo_actual >= limite:
        raise PermissionDenied(
            f"Tu plan '{plan.nombre}' permite hasta {limite} {nombre_recurso}. "
            f"Actualiza tu plan para agregar más."
        )
