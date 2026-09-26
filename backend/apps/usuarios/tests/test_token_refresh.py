"""
Refrescos concurrentes del mismo refresh token (misma cuenta abierta en
varias pestañas/dispositivos) -- ver ``MyTokenRefreshSerializer``.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.testing import BaseTenantTestCase
from apps.usuarios.api.serializers import MyTokenRefreshSerializer


class RefreshConcurrenteTests(BaseTenantTestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="cajero", password="Secreta123!")
        self.refresh = str(RefreshToken.for_user(self.user))

    def _refrescar(self, token):
        serializer = MyTokenRefreshSerializer(data={"refresh": token})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def test_reuso_inmediato_devuelve_el_mismo_par(self):
        primero = self._refrescar(self.refresh)
        segundo = self._refrescar(self.refresh)
        self.assertEqual(primero, segundo)
        # El par nuevo sigue siendo utilizable.
        self.assertIn("access", self._refrescar(primero["refresh"]))

    @override_settings(JWT_REFRESH_REUSE_GRACE_SECONDS=0)
    def test_sin_ventana_de_gracia_el_reuso_se_rechaza(self):
        self._refrescar(self.refresh)
        with self.assertRaises((ValidationError, TokenError)):
            self._refrescar(self.refresh)

    def test_token_desconocido_no_usa_la_cache(self):
        with self.assertRaises((ValidationError, TokenError)):
            self._refrescar("token-invalido")
