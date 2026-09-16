from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.response import error_response, standard_response
from apps.core.throttling import ResilientScopedRateThrottle
from apps.usuarios.services.password_reset_service import (
    ResetTokenInvalidoError,
    confirmar_reset,
    solicitar_reset,
)


def _tenant_frontend_url(request) -> str:
    """
    URL base del panel del tenant en el frontend, para armar el link del
    correo de recuperación. En dev el frontend vive en el puerto 3000 del
    mismo subdominio que el backend; en producción se puede fijar
    explícitamente vía `FRONTEND_BASE_DOMAIN`.
    """
    from django.conf import settings

    schema = request.tenant.schema_name
    base_domain = getattr(settings, "FRONTEND_BASE_DOMAIN", "localhost:3000")
    return f"http://{schema}.{base_domain}"


class PasswordResetRequestView(APIView):
    """Pide el email y envía el enlace de recuperación (si existe un usuario con ese email)."""

    permission_classes = [AllowAny]
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        if not email:
            return error_response([{"code": "required", "detail": "El email es requerido.", "field": "email"}])

        solicitar_reset(email, _tenant_frontend_url(request))
        # Mensaje idéntico exista o no el email: evita que alguien use este
        # endpoint para averiguar qué correos están registrados.
        return standard_response(data={"message": "Si el correo existe, te enviamos instrucciones para recuperar tu contraseña."})


class PasswordResetConfirmView(APIView):
    """Recibe uid/token del enlace del correo + la nueva contraseña."""

    permission_classes = [AllowAny]
    throttle_classes = [ResilientScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        nueva_password = request.data.get("new_password")

        if not all([uid, token, nueva_password]):
            return error_response([{"code": "required", "detail": "Faltan datos requeridos.", "field": None}])
        if len(nueva_password) < 8:
            return error_response([{"code": "invalid", "detail": "La contraseña debe tener al menos 8 caracteres.", "field": "new_password"}])

        try:
            confirmar_reset(uid, token, nueva_password)
        except ResetTokenInvalidoError as e:
            return error_response([{"code": "invalid_token", "detail": str(e), "field": None}])

        return standard_response(data={"message": "Contraseña actualizada. Ya puedes iniciar sesión."})
