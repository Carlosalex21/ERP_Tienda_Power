"""Cambiar la contraseña cierra las demás sesiones y exige una contraseña robusta."""
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.testing import BaseTenantTestCase
from apps.usuarios.api.serializers import MyTokenRefreshSerializer
from apps.usuarios.api.views_auth import CambiarPasswordView
from apps.usuarios.models import UserMetadata


class CambiarPasswordTests(BaseTenantTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cajera", password="Clave-Vieja-2026")
        UserMetadata.objects.get_or_create(user=self.user)
        self.otra_sesion = str(RefreshToken.for_user(self.user))

    def _cambiar(self, actual, nueva):
        request = APIRequestFactory().post("/x", {"password_actual": actual, "password_nueva": nueva}, format="json")
        force_authenticate(request, user=self.user)
        return CambiarPasswordView.as_view()(request)

    def test_rechaza_contrasena_debil(self):
        respuesta = self._cambiar("Clave-Vieja-2026", "12345678")
        self.assertEqual(respuesta.status_code, 400)

    def test_revoca_otras_sesiones_y_entrega_par_nuevo(self):
        respuesta = self._cambiar("Clave-Vieja-2026", "Otra-Clave-Segura-77")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        datos = respuesta.data["data"] if "data" in respuesta.data else respuesta.data
        self.assertIn("refresh", datos)

        with self.assertRaises((TokenError, ValidationError)):
            MyTokenRefreshSerializer(data={"refresh": self.otra_sesion}).is_valid(raise_exception=True)

        nueva = MyTokenRefreshSerializer(data={"refresh": datos["refresh"]})
        self.assertTrue(nueva.is_valid(), nueva.errors)
