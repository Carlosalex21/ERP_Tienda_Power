"""
ASGI config for backend project.

Sirve tanto HTTP normal (Django de siempre) como WebSockets (Channels) --
`ProtocolTypeRouter` separa el tráfico por protocolo desde el nivel más
externo. El HTTP sigue exactamente igual que antes (`get_asgi_application()`,
misma app de Django con `django-tenants`); solo se le suma el árbol de
WebSockets envuelto en `TenantJWTAuthMiddleware` (ver
`apps.core.channels_middleware`), que resuelve tenant + usuario igual que
`TenantMainMiddleware`/`TenantBoundJWTAuthentication` lo hacen para HTTP.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django  # noqa: E402
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from apps.core.channels_middleware import TenantJWTAuthMiddleware  # noqa: E402
from apps.restaurantes.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TenantJWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
