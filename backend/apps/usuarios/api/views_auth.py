from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.response import error_response, standard_response
from apps.core.permissions import ROL_ADMIN, codigo_rol
from apps.core.throttling import ResilientScopedRateThrottle as ScopedRateThrottle
from apps.usuarios.services.login_attempt_service import (
    limpiar_intentos,
    registrar_intento_fallido,
    registrar_intento_login,
    usuario_esta_bloqueado,
)
from .serializers import MyTokenObtainPairSerializer, UserMeSerializer

# Tenant y usuario del demo público enlazado desde la landing ("Probar demo
# en vivo") -- fijos a propósito (nunca vienen del request) para que
# `DemoAutoLoginView` no se pueda convertir en un bypass de autenticación
# para un tenant real. Deben coincidir con lo que siembra
# `apps.tenants.management.commands.seed_demo_tenant`.
DEMO_TENANT_SCHEMA = "demo"
DEMO_USERNAME = "demo"


class IsAdmin(BasePermission):
    """Permite solo a usuarios con rol 'Administrador'."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        metadata = getattr(request.user, "metadata", None)
        return bool(metadata) and codigo_rol(metadata.rol) == ROL_ADMIN


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


class DemoAutoLoginView(APIView):
    """
    Emite un access/refresh token para el usuario demo público, sin
    contraseña -- pensado para el botón "Probar demo en vivo" de la landing.

    Solo funciona para el tenant/usuario fijos de arriba: no acepta ningún
    dato del request que determine a quién loguea, así que no sirve como
    bypass de login para un tenant real. El schema del tenant demo se activa
    explícitamente porque este endpoint se llama desde el dominio raíz (la
    landing), que resuelve al esquema público -- ahí no existe el usuario
    demo, que vive en su propio esquema de tenant.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "demo_login"

    def post(self, request, *args, **kwargs):
        from django.contrib.auth import get_user_model
        from django_tenants.utils import schema_context
        from apps.tenants.models import Client

        try:
            tenant = Client.objects.get(schema_name=DEMO_TENANT_SCHEMA)
        except Client.DoesNotExist:
            return error_response(
                [{"code": "demo_unavailable", "detail": "La demo no está disponible en este momento.", "field": None}],
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        dominio = tenant.domains.filter(is_primary=True).first()
        if dominio is None:
            return error_response(
                [{"code": "demo_unavailable", "detail": "La demo no está disponible en este momento.", "field": None}],
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        with schema_context(DEMO_TENANT_SCHEMA):
            User = get_user_model()
            try:
                user = User.objects.get(username=DEMO_USERNAME, is_active=True)
            except User.DoesNotExist:
                return error_response(
                    [{"code": "demo_unavailable", "detail": "La demo no está disponible en este momento.", "field": None}],
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            # Reutiliza el mismo serializer del login normal para que el
            # token demo lleve exactamente los mismos claims (rol, sucursal,
            # schema_name) que uno emitido con contraseña -- así el panel no
            # necesita ninguna rama de código especial para la sesión demo.
            token = MyTokenObtainPairSerializer.get_token(user)

        return standard_response(data={
            "access": str(token.access_token),
            "refresh": str(token),
            "tenant_domain": dominio.domain,
        })


class UserMeView(APIView):
    """
    Vista para obtener los datos del usuario actualmente autenticado.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserMeSerializer

    def get(self, request):
        serializer = self.serializer_class(request.user.metadata)
        return standard_response(data=serializer.data)


class CambiarPasswordView(APIView):
    """
    Autoservicio: el usuario autenticado cambia SU PROPIA contraseña.
    Distinto del reseteo de otro usuario por un admin (`UserManagementViewSet`)
    y del flujo de "olvidé mi contraseña" (`PasswordResetConfirmView`, sin
    sesión) -- este exige la contraseña actual porque quien lo llama ya
    tiene una sesión válida y solo se está protegiendo de que alguien con
    el dispositivo desbloqueado se la cambie sin saberla.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        actual = request.data.get("password_actual")
        nueva = request.data.get("password_nueva")

        if not actual or not nueva:
            return error_response([{"code": "required", "detail": "Faltan datos requeridos.", "field": None}])
        if len(nueva) < 8:
            return error_response([{"code": "invalid", "detail": "La nueva contraseña debe tener al menos 8 caracteres.", "field": "password_nueva"}])
        if not request.user.check_password(actual):
            return error_response([{"code": "invalid", "detail": "La contraseña actual no es correcta.", "field": "password_actual"}])

        request.user.set_password(nueva)
        request.user.save(update_fields=["password"])
        return standard_response(data={"message": "Contraseña actualizada."})
