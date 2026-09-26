"""
Middleware de Channels que replica, para WebSockets, lo que
`TenantMainMiddleware` + `TenantBoundJWTAuthentication` hacen para HTTP:
resuelve el tenant a partir del Host de la conexión y, si viene un JWT
válido PARA ESE tenant (cookie o `?token=`), resuelve también `scope["user"]`.

Se implementa a mano (no se reutiliza `channels.auth.AuthMiddlewareStack`,
pensado para sesiones de Django) porque este proyecto autentica con JWT y
además necesita el mismo aislamiento por schema que ya resuelve
`apps.core.authentication.TenantBoundJWTAuthentication` para HTTP -- un
token válido emitido en el esquema A jamás debe autenticar en el esquema B.
"""
from __future__ import annotations

from http.cookies import SimpleCookie

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django_tenants.utils import get_public_schema_name, schema_context


def _hostname_from_scope(scope) -> str | None:
    headers = dict(scope.get('headers') or [])
    host = headers.get(b'host')
    if not host:
        return None
    return host.decode('latin-1').split(':')[0]


def _token_from_scope(scope) -> str | None:
    headers = dict(scope.get('headers') or [])
    nombre_cookie = getattr(settings, 'JWT_ACCESS_COOKIE_NAME', 'access_token')
    raw_cookie = headers.get(b'cookie')
    if raw_cookie:
        cookie = SimpleCookie()
        cookie.load(raw_cookie.decode('latin-1'))
        morsel = cookie.get(nombre_cookie)
        if morsel:
            return morsel.value
    # Fallback `?token=` -- por si el frontend prefiere mandarlo así en vez
    # de depender de que la cookie viaje en el handshake del WebSocket.
    query_string = (scope.get('query_string') or b'').decode()
    for par in query_string.split('&'):
        if par.startswith('token='):
            return par[len('token='):]
    return None


@database_sync_to_async
def _resolver_tenant(hostname: str):
    from apps.tenants.models import Domain
    with schema_context(get_public_schema_name()):
        domain = Domain.objects.select_related('tenant').filter(domain=hostname).first()
        return domain.tenant if domain else None


@database_sync_to_async
def _resolver_usuario(schema_name: str, token_str: str):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import AnonymousUser
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        token = AccessToken(token_str)
    except Exception:
        return AnonymousUser()

    token_schema = token.get('schema_name')
    if token_schema is None:
        if schema_name != get_public_schema_name():
            return AnonymousUser()
    elif token_schema != schema_name:
        return AnonymousUser()

    User = get_user_model()
    with schema_context(schema_name):
        try:
            return User.objects.get(pk=token['user_id'])
        except User.DoesNotExist:
            return AnonymousUser()


class TenantJWTAuthMiddleware(BaseMiddleware):
    """Puebla `scope['tenant']`, `scope['schema_name']` y `scope['user']` para un consumer."""

    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser

        scope = dict(scope)
        scope['tenant'] = None
        scope['schema_name'] = None
        scope['user'] = AnonymousUser()

        hostname = _hostname_from_scope(scope)
        if hostname:
            tenant = await _resolver_tenant(hostname)
            if tenant is not None:
                scope['tenant'] = tenant
                scope['schema_name'] = tenant.schema_name
                token_str = _token_from_scope(scope)
                if token_str:
                    scope['user'] = await _resolver_usuario(tenant.schema_name, token_str)

        return await self.inner(scope, receive, send)
