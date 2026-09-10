from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.response import error_response, standard_response
from apps.usuarios.services.login_attempt_service import (
    limpiar_intentos,
    registrar_intento_fallido,
    registrar_intento_login,
    usuario_esta_bloqueado,
)
from .serializers import MyTokenObtainPairSerializer, UserMeSerializer


class IsAdmin(BasePermission):
    """Permite solo a usuarios con rol 'Administrador'."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        metadata = getattr(request.user, "metadata", None)
        return bool(metadata and metadata.rol and metadata.rol.nombre == "Administrador")


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Obtiene el par access/refresh con bloqueo por intentos fallidos.

    Limita a ``10/min`` por IP mediante el scope de throttle ``login``.
    """

    permission_classes = [AllowAny]
    serializer_class = MyTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        ip = self._client_ip(request)
        username = request.data.get("username")
        user = self._find_user(username)

        # Bloqueo temporal por intentos fallidos (Zero Trust).
        if user is not None and usuario_esta_bloqueado(user):
            return error_response(
                [{
                    "code": "account_locked",
                    "detail": "Cuenta bloqueada temporalmente por intentos fallidos. Intente más tarde.",
                    "field": None,
                }],
                status_code=status.HTTP_423_LOCKED,
            )

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as exc:
            # Registramos el intento fallido y bloqueamos si supera el umbral.
            if user is not None:
                registrar_intento_fallido(user=user, ip=ip)
            # Reutiliza el exception handler global para estandarizar el error.
            from rest_framework.views import exception_handler
            response = exception_handler(exc, {"request": request, "view": self})
            if response is not None:
                return response
            raise

        # Login exitoso: limpiamos intentos fallidos previos.
        if user is not None:
            registrar_intento_login(user=user, ip=ip, success=True)
            limpiar_intentos(user)

        data = serializer.validated_data
        return standard_response(data=data, status_code=status.HTTP_200_OK)

    @staticmethod
    def _client_ip(request) -> str | None:
        """Extrae la IP del cliente desde la petición (con proxies)."""
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    @staticmethod
    def _find_user(username: str | None):
        """Busca el usuario por username; None si no existe o no se provee."""
        if not username:
            return None
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None


class UserMeView(APIView):
    """
    Vista para obtener los datos del usuario actualmente autenticado.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserMeSerializer

    def get(self, request):
        serializer = self.serializer_class(request.user.metadata)
        return standard_response(data=serializer.data)
