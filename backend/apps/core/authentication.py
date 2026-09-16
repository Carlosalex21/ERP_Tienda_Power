"""
Autenticación JWT con verificación de aislamiento multi-tenant.

SimpleJWT por sí solo valida la firma del token y busca el ``user_id`` en la
tabla ``auth_user`` del esquema activo. Como cada tenant tiene su propio
esquema con IDs de usuario independientes, un token válido emitido en el
esquema A puede autenticar por accidente como el usuario con el mismo id en
el esquema B. Esta clase cierra ese hueco comparando el claim
``schema_name`` embebido al emitir el token (ver
``apps.usuarios.api.serializers.MyTokenObtainPairSerializer.get_token``)
contra el esquema realmente activo para la request.
"""
from __future__ import annotations

from django.db import connection
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class TenantBoundJWTAuthentication(JWTAuthentication):
    """JWTAuthentication que exige que el token pertenezca al tenant activo."""

    def get_user(self, validated_token):
        active_schema = getattr(connection, "schema_name", None)
        token_schema = validated_token.get("schema_name")

        if token_schema is None:
            # Tokens emitidos en el esquema público (dueños de tenant, ver
            # backend.urls_public) no llevan este claim; solo son válidos
            # mientras la request siga resolviendo al esquema 'public'.
            if active_schema != "public":
                raise AuthenticationFailed(
                    "El token no pertenece a este tenant.", code="tenant_mismatch"
                )
        elif token_schema != active_schema:
            raise AuthenticationFailed(
                "El token no pertenece a este tenant.", code="tenant_mismatch"
            )

        return super().get_user(validated_token)
