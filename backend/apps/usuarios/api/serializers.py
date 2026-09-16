"""
Serializers de autenticación y perfil de usuario del tenant.

Incluye los serializers personalizados de SimpleJWT para añadir claims
(rol, sucursal, tenant) a los tokens, y el serializer de refresh que
aprovecha la rotación con lista negra configurada en ``SIMPLE_JWT``.
"""
from __future__ import annotations

from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.exceptions import InvalidToken
from django.contrib.auth import authenticate
from django.db import connection
from django_tenants.utils import get_public_schema_name
from ..models import Rol, UserMetadata


class RolSerializer(serializers.ModelSerializer):
    """Rol del tenant, para poblar selects (ej. al invitar un empleado)."""

    class Meta:
        model = Rol
        fields = ("id", "codigo", "nombre", "descripcion", "activo")


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


class MyTokenRefreshSerializer(TokenRefreshSerializer):
    """Rotación de refresh token propagando los claims personalizados."""

    def validate(self, attrs):
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
    sucursal = serializers.CharField(
        source="sucursal.nombre", read_only=True, allow_null=True
    )

    class Meta:
        model = UserMetadata
        fields = ("id", "email", "first_name", "last_name", "rol", "sucursal")
