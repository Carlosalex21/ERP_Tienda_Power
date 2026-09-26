"""
Sesiones (JWT) de un usuario: validación de contraseñas y revocación.

Un JWT de acceso vive como mucho ``ACCESS_TOKEN_LIFETIME`` (15 min), pero
los refresh tokens duran días. Sin revocarlos, cambiar la contraseña --
justo lo que haría alguien que sospecha que le robaron la sesión -- dejaba
vivas todas las sesiones abiertas en otros navegadores/dispositivos.
"""
from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken


class ContrasenaInvalidaError(Exception):
    """La contraseña nueva no cumple ``AUTH_PASSWORD_VALIDATORS``."""

    def __init__(self, mensajes: list[str]):
        super().__init__(" ".join(mensajes))
        self.mensajes = mensajes


def validar_contrasena(nueva: str, user=None) -> None:
    """Aplica los validadores de Django (longitud, comunes, numéricas, parecida al usuario)."""
    try:
        validate_password(nueva, user=user)
    except ValidationError as exc:
        raise ContrasenaInvalidaError(list(exc.messages)) from exc


def revocar_sesiones(user) -> int:
    """Invalida TODOS los refresh tokens emitidos al usuario. Devuelve cuántos se revocaron."""
    revocados = 0
    for token in OutstandingToken.objects.filter(user=user).exclude(blacklistedtoken__isnull=False):
        _, creado = BlacklistedToken.objects.get_or_create(token=token)
        revocados += int(creado)
    return revocados


def emitir_sesion(user) -> dict[str, str]:
    """Par nuevo de tokens (mismos claims que el login normal) para la sesión actual."""
    from apps.usuarios.api.serializers import MyTokenObtainPairSerializer

    refresh: RefreshToken = MyTokenObtainPairSerializer.get_token(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
