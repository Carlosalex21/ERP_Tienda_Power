"""
Test del endpoint de roles (`GET /api/v1/auth/roles/`).

Antes de este endpoint, el frontend de RRHH hardcodeaba 3 roles con IDs fijos
sin garantía de que coincidieran con los del tenant. El endpoint anterior
(`views_users.RolViewSet`) nunca funcionó -- importaba un `RolSerializer`
que no existía y nunca estuvo registrado en ninguna URL, así que el
`ImportError` real nunca se detectó.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.testing import BaseTenantTestCase as TenantTestCase
from apps.usuarios.api.views_roles import RolViewSet

from ..models import Rol, UserMetadata

User = get_user_model()


class RolesEndpointTests(TenantTestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.rol_admin = Rol.objects.create(nombre='Administrador', codigo='admin')
        Rol.objects.create(nombre='Vendedor', codigo='vendedor')
        Rol.objects.create(nombre='Inactivo', codigo='inactivo', activo=False)

        self.admin_user = User.objects.create_user(username='admin-roles', password='x')
        UserMetadata.objects.create(user=self.admin_user, rol=self.rol_admin)

    def test_listar_roles_devuelve_solo_activos(self):
        request = self.factory.get('/api/v1/auth/roles/')
        force_authenticate(request, user=self.admin_user)
        response = RolViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200, response.data)
        nombres = {r['nombre'] for r in response.data}
        self.assertEqual(nombres, {'Administrador', 'Vendedor'})

    def test_listar_roles_requiere_admin(self):
        rol_vendedor = Rol.objects.get(codigo='vendedor')
        vendedor_user = User.objects.create_user(username='vendedor-roles', password='x')
        UserMetadata.objects.create(user=vendedor_user, rol=rol_vendedor)

        request = self.factory.get('/api/v1/auth/roles/')
        force_authenticate(request, user=vendedor_user)
        response = RolViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 403)
