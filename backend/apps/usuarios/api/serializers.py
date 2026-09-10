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
from ..models import UserMetadata


def _tenant_schema() -> str | None:
    """Devuelve el schema_name del tenant actual si existe."""
    return getattr(connection, "schema_name", None)


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

        metadata = getattr(user, "metadata", None)
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
        if "access" in data:
            from rest_framework_simplejwt.tokens import RefreshToken

            refresh = RefreshToken(attrs["refresh"])
            user_id = refresh.get("user_id")
            if user_id:
                from django.contrib.auth import get_user_model

                try:
                    user = get_user_model().objects.get(pk=user_id)
                    access_token = RefreshToken(data["access"]).access_token
                    access_token["username"] = user.username
                    access_token["schema_name"] = _tenant_schema()
                    metadata = getattr(user, "metadata", None)
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
