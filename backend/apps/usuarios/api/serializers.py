"""
Serializers de autenticación y perfil de usuario del tenant.

Incluye los serializers personalizados de SimpleJWT para añadir claims
(rol, sucursal, tenant) a los tokens, y el serializer de refresh que
aprovecha la rotación con lista negra configurada en ``SIMPLE_JWT``.
"""
from __future__ import annotations

import hashlib
import time

from django.conf import settings
from django.core.cache import cache
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.exceptions import InvalidToken
from django.contrib.auth import authenticate
from django.db import connection
from django_tenants.utils import get_public_schema_name
from apps.core.cache_utils import cache_key, get_cached, set_cached
from ..models import Rol, UserMetadata


class RolSerializer(serializers.ModelSerializer):
    """
    Rol del tenant, para poblar selects (ej. al invitar un empleado) y para
    la pantalla de "Permisos por Rol" (`modulos_ocultos`, ver `RolViewSet`).
    """

    class Meta:
        model = Rol
        fields = ("id", "codigo", "nombre", "descripcion", "activo", "modulos_ocultos")
        # `codigo` es el identificador estable que compara todo el sistema
        # de permisos (ver `apps.core.permissions.codigo_rol`) -- dejarlo
        # editable desde este mismo endpoint (ahora que `RolViewSet` acepta
        # PATCH para `modulos_ocultos`) podría desincronizarlo en silencio.
        read_only_fields = ("codigo", "nombre", "descripcion", "activo")


def _tenant_schema() -> str | None:
    """Devuelve el schema_name del tenant actual si existe."""
    return getattr(connection, "schema_name", None)


def _metadata_o_none(user):
    """
    `UserMetadata` es un modelo de TENANT_APPS: su tabla no existe en el
    esquema público. `TOKEN_OBTAIN_SERIALIZER`/`TOKEN_REFRESH_SERIALIZER` se
    configuran una sola vez a nivel de proyecto (ver `SIMPLE_JWT` en
    settings.py) y por eso este serializer también se usa para el login del
    dueño de un tenant en el esquema público (ver `apps.tenants.urls`) --
    ahí `getattr(user, "metadata", None)` no captura un "no existe" limpio,
    sino un `ProgrammingError` (tabla inexistente) porque el descriptor de
    Django solo convierte en `AttributeError` el caso "no hay fila", no el
    caso "no hay tabla".
    """
    if _tenant_schema() == get_public_schema_name():
        return None
    return getattr(user, "metadata", None)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Añade claims de rol, sucursal y tenant al access token."""

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")

        # Autenticamos explícitamente respetando el esquema activo del tenant
        user = authenticate(username=username, password=password)

        if user is None:
            raise InvalidToken("No active account found with the given credentials")

        if not user.is_active:
            raise InvalidToken("User is inactive")

        # Generamos los tokens utilizando el comportamiento estándar de SimpleJWT
        data = super().validate(attrs)
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["schema_name"] = _tenant_schema()

        metadata = _metadata_o_none(user)
        if metadata is not None:
            if metadata.rol:
                token["rol"] = metadata.rol.nombre
                token["rol_id"] = metadata.rol_id
            if metadata.sucursal:
                token["sucursal"] = metadata.sucursal.nombre
                token["sucursal_id"] = metadata.sucursal_id
        else:
            token["rol"] = None
            token["sucursal"] = None

        return token


def _refresh_grace_seconds() -> int:
    return int(getattr(settings, "JWT_REFRESH_REUSE_GRACE_SECONDS", 30))


def _refresh_grace_key(raw_refresh: str) -> str:
    """Clave (aislada por tenant) del resultado de rotar ``raw_refresh``; se hashea para no guardar el token en claro."""
    digest = hashlib.sha256(raw_refresh.encode()).hexdigest()
    return cache_key("jwt_refresh_rotado", digest)


def _tomar_turno_de_rotacion(grace_key: str, ttl: int) -> bool:
    """
    ``True`` si esta petición es la que debe rotar. Con Redis caído se
    degrada a "sí" (mismo comportamiento que antes de la ventana de gracia).
    """
    try:
        return bool(cache.add(f"{grace_key}:lock", 1, timeout=ttl))
    except Exception:  # noqa: BLE001 - un caché caído no debe bloquear el refresh
        return True


def _esperar_rotacion_ajena(grace_key: str, max_espera: float = 3.0):
    """Espera (poco) a que la petición que ganó el turno publique el par rotado."""
    limite = time.monotonic() + max_espera
    while time.monotonic() < limite:
        previo = get_cached(grace_key)
        if previo:
            return previo
        time.sleep(0.05)
    return None


class MyTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Rotación de refresh token propagando los claims personalizados.

    Ventana de gracia ante refrescos concurrentes: con
    ``ROTATE_REFRESH_TOKENS`` + ``BLACKLIST_AFTER_ROTATION`` el primer
    refresh invalida el token viejo, así que si dos pestañas (o dos
    peticiones de la misma pestaña) lo presentan casi a la vez, la segunda
    recibía ``401 Token is blacklisted`` y el frontend cerraba la sesión --
    el origen del "se queda pegado" con la misma cuenta abierta en varias
    ventanas. Durante unos segundos tras la rotación, presentar el MISMO
    token viejo devuelve el MISMO par nuevo ya emitido (no uno adicional),
    así que no se amplía la superficie: solo quien ya poseía ese token exacto
    obtiene lo que igual habría recibido la otra pestaña.
    """

    def validate(self, attrs):
        raw_refresh = attrs.get("refresh") or ""
        grace = _refresh_grace_seconds()
        grace_key = _refresh_grace_key(raw_refresh) if raw_refresh and grace > 0 else None
        if grace_key:
            previo = get_cached(grace_key)
            if previo:
                return previo
            # Dos peticiones llegando en el mismo instante (workers
            # distintos): solo una rota, la otra espera su resultado.
            if not _tomar_turno_de_rotacion(grace_key, grace):
                previo = _esperar_rotacion_ajena(grace_key)
                if previo:
                    return previo

        data = self._rotar(attrs)
        if grace_key:
            set_cached(grace_key, data, ttl=grace)
        return data

    def _rotar(self, attrs):
        data = super().validate(attrs)
        # Si SimpleJWT ya rotó el token y devolvió un nuevo access/refresh,
        # replicamos los claims de usuario al nuevo access token.
        #
        # OJO: con ROTATE_REFRESH_TOKENS+BLACKLIST_AFTER_ROTATION, el
        # `super().validate()` de arriba YA puso `attrs["refresh"]` (el
        # token original) en la blacklist como parte de la rotación. Antes,
        # esta función volvía a construir `RefreshToken(attrs["refresh"])`
        # para leer el `user_id` -- pero el constructor de `RefreshToken`
        # verifica el token (incluida la blacklist), así que SIEMPRE
        # reventaba con "Token is blacklisted" y el refresh nunca
        # funcionaba en ningún esquema (ni tenant ni público). Además
        # `RefreshToken(data["access"])` estaba parseando un ACCESS token
        # como si fuera un REFRESH token (tipo equivocado). Se leen los
        # claims directamente del nuevo `access` (ya válido, nunca
        # blacklisteado) con `AccessToken`, sin re-tocar el token viejo.
        if "access" in data:
            from rest_framework_simplejwt.tokens import AccessToken

            try:
                access_token = AccessToken(data["access"])
                user_id = access_token.get("user_id")
                if user_id:
                    from django.contrib.auth import get_user_model

                    user = get_user_model().objects.get(pk=user_id)
                    access_token["username"] = user.username
                    access_token["schema_name"] = _tenant_schema()
                    metadata = _metadata_o_none(user)
                    if metadata is not None and metadata.rol:
                        access_token["rol"] = metadata.rol.nombre
                    data["access"] = str(access_token)
            except Exception:  # noqa: BLE001 - No bloquear el refresh.
                pass
        return data


class UserMeSerializer(serializers.ModelSerializer):
    """
    Serializer para el endpoint /me, mostrando los datos del usuario actual.
    """

    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    rol = serializers.CharField(source="rol.nombre", read_only=True, allow_null=True)
    rol_codigo = serializers.CharField(source="rol.codigo", read_only=True, allow_null=True)
    sucursal = serializers.CharField(
        source="sucursal.nombre", read_only=True, allow_null=True
    )
    departamento = serializers.CharField(
        source="departamento.nombre", read_only=True, allow_null=True
    )
    departamento_id = serializers.IntegerField(read_only=True, allow_null=True)
    # Módulos que el panel debe ocultarle a ESTE usuario según su rol (ver
    # `Rol.modulos_ocultos` y la pantalla de "Permisos por Rol"). Se calcula
    # aquí (no en un endpoint aparte) porque cualquier empleado ya puede
    # consultar `/auth/me/` -- así ve solo lo que le toca A ÉL, sin
    # necesitar el acceso admin-only que sí exige `RolViewSet` para listar
    # TODOS los roles.
    modulos_ocultos = serializers.SerializerMethodField()

    def get_modulos_ocultos(self, obj) -> list[str]:
        return obj.rol.modulos_ocultos if obj.rol else []

    class Meta:
        model = UserMetadata
        fields = ("id", "email", "first_name", "last_name", "rol", "rol_codigo", "sucursal", "departamento", "departamento_id", "modulos_ocultos")
