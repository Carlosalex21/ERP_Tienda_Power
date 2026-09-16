"""
Tests de `apps.core.permissions`.

Estas clases nunca se ejercitaron en un test hasta ahora -- un
`NameError` real (`_codigo_rol` renombrado a `codigo_rol` sin actualizar
las dos líneas que lo llamaban) llegó a producción sin que ninguna
verificación lo atrapara, porque `manage.py check`/`makemigrations --check`
no ejecutan el cuerpo de las funciones. Como `apps.core` no está registrado
en `INSTALLED_APPS` (ver hallazgo de la auditoría), estos tests viven aquí
en vez de en `apps/core/tests/`.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.testing import BaseTenantTestCase as TenantTestCase
from apps.core.permissions import IsTenantAdmin, IsAdminOrVendedor

from ..models import Rol, UserMetadata

User = get_user_model()


class PermissionsTests(TenantTestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.rol_admin = Rol.objects.create(nombre='Administrador', codigo='admin')
        self.rol_vendedor = Rol.objects.create(nombre='Vendedor', codigo='vendedor')
        self.rol_sin_codigo = Rol.objects.create(nombre='Almacenista')  # rol legado, sin `codigo`

        self.user_admin = User.objects.create_user(username='admin-user', password='x')
        UserMetadata.objects.create(user=self.user_admin, rol=self.rol_admin)

        self.user_vendedor = User.objects.create_user(username='vendedor-user', password='x')
        UserMetadata.objects.create(user=self.user_vendedor, rol=self.rol_vendedor)

        self.user_legado = User.objects.create_user(username='almacenista-user', password='x')
        UserMetadata.objects.create(user=self.user_legado, rol=self.rol_sin_codigo)

    def _request_para(self, user):
        request = self.factory.get('/')
        force_authenticate(request, user=user)
        request.user = user
        return request

    def test_is_tenant_admin_permite_a_administrador(self):
        self.assertTrue(IsTenantAdmin().has_permission(self._request_para(self.user_admin), None))

    def test_is_tenant_admin_rechaza_a_vendedor(self):
        self.assertFalse(IsTenantAdmin().has_permission(self._request_para(self.user_vendedor), None))

    def test_is_admin_or_vendedor_permite_a_ambos(self):
        perm = IsAdminOrVendedor()
        self.assertTrue(perm.has_permission(self._request_para(self.user_admin), None))
        self.assertTrue(perm.has_permission(self._request_para(self.user_vendedor), None))

    def test_rol_legado_sin_codigo_usa_fallback_por_nombre(self):
        # "Almacenista" no tiene `codigo` seteado: debe resolverse igual vía
        # el mapa de fallback por nombre, no reventar ni negar todo.
        self.assertFalse(IsTenantAdmin().has_permission(self._request_para(self.user_legado), None))
