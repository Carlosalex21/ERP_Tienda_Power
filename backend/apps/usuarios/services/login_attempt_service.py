"""
Servicio de bloqueo por intentos fallidos de inicio de sesión (Zero Trust).

Registra cada intento de login, cuenta los **fallos dentro de una ventana de
tiempo** (por defecto 5 en 15 minutos) y bloquea temporalmente la cuenta
marcando ``UserMetadata.bloqueado_hasta`` y desactivando ``user.is_active``.
Cuando la ventana expira, la cuenta se reactiva automáticamente en el
siguiente intento de login.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.utils import timezone

from ..models import LoginAttempt, UserMetadata


def _max_intentos() -> int:
    """Número máximo de intentos fallidos antes de bloquear la cuenta."""
    return int(getattr(settings, "LOGIN_MAX_INTENTOS", 5))


def _ventana() -> timedelta:
    """Ventana de tiempo durante la cual se cuentan los intentos fallidos."""
    return timedelta(minutes=int(getattr(settings, "LOGIN_VENTANA_MINUTOS", 15)))


def _get_or_create_metadata(user) -> Optional[UserMetadata]:
    """Devuelve (o crea) el metadata del usuario; None si no puede crearse."""
    metadata = getattr(user, "metadata", None)
    if metadata is not None:
        return metadata
    if user.pk is not None:
        metadata, _ = UserMetadata.objects.get_or_create(user=user)
        return metadata
    return None


def registrar_intento_login(
    *,
    user,
    ip: Optional[str] = None,
    success: bool,
) -> None:
    """
    Registra un intento de login (éxito o fallo).

    Args:
        user: Usuario que intenta autenticarse.
        ip: Dirección IP del cliente (opcional).
        success: ``True`` si el login fue exitoso.
    """
    LoginAttempt.objects.create(user=user, ip=ip, success=success)


def limpiar_intentos(user) -> None:
    """Elimina los intentos fallidos del usuario tras un login exitoso."""
    LoginAttempt.objects.filter(user=user, success=False).delete()


def contar_intentos_fallidos_recientes(user) -> int:
    """
    Cuenta los intentos fallidos del usuario dentro de la ventana de tiempo.

    Args:
        user: Usuario a evaluar.

    Returns:
        int: Número de fallos en la ventana.
    """
    inicio = timezone.now() - _ventana()
    return LoginAttempt.objects.filter(
        user=user,
        success=False,
        timestamp__gte=inicio,
    ).count()


def usuario_esta_bloqueado(user) -> bool:
    """
    Indica si la cuenta está bloqueada temporalmente.

    Si el bloqueo expiró, reactiva la cuenta automáticamente.

    Args:
        user: Usuario a evaluar.

    Returns:
        bool: ``True`` si la cuenta sigue bloqueada.
    """
    metadata = _get_or_create_metadata(user)
    if metadata is None or metadata.bloqueado_hasta is None:
        return False

    if metadata.bloqueado_hasta <= timezone.now():
        # El bloqueo expiró: reactivamos automaticamente.
        metadata.bloqueado_hasta = None
        metadata.save(update_fields=["bloqueado_hasta"])
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        return False

    return True


def registrar_intento_fallido(
    *,
    user,
    ip: Optional[str] = None,
) -> bool:
    """
    Registra un intento fallido y bloquea la cuenta si supera el umbral.

    Args:
        user: Usuario que falló al autenticarse.
        ip: Dirección IP del cliente (opcional).

    Returns:
        bool: ``True`` si la cuenta quedó bloqueada tras este fallo.
    """
    registrar_intento_login(user=user, ip=ip, success=False)

    if contar_intentos_fallidos_recientes(user) >= _max_intentos():
        metadata = _get_or_create_metadata(user)
        if metadata is not None:
            metadata.bloqueado_hasta = timezone.now() + _ventana()
            metadata.save(update_fields=["bloqueado_hasta"])
        user.is_active = False
        user.save(update_fields=["is_active"])
        return True

    return False
