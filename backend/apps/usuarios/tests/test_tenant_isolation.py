"""
Test end-to-end del aislamiento multi-tenant vía JWT.

Cubre el hallazgo más crítico de la auditoría de arquitectura: antes de
``TenantBoundJWTAuthentication`` (``apps.core.authentication``), SimpleJWT
solo validaba la firma del token y buscaba ``user_id`` en la tabla
``auth_user`` del esquema *activo* -- sin comprobar a qué tenant pertenecía
ese token. Como cada schema tiene su propia tabla de usuarios con IDs
independientes, un token emitido en el tenant A podía autenticar contra
cualquier usuario del tenant B con el mismo id.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django_tenants.utils import get_tenant_domain_model, get_tenant_model, schema_context
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import AccessToken

from apps.core.authentication import TenantBoundJWTAuthentication

TenantModel = get_tenant_model()
DomainModel = get_tenant_domain_model()
PublicUser = get_user_model()


def _crear_tenant(schema_name: str):
    owner, _ = PublicUser.objects.get_or_create(
        username=f'owner-{schema_name}',
        defaults={'email': f'{schema_name}@example.com'},
    )
    tenant = TenantModel(
        schema_name=schema_name,
        nombre_empresa=schema_name,
        email_contacto=f'{schema_name}@example.com',
        owner=owner,
    )
    tenant.save(verbosity=0)
    DomainModel.objects.create(tenant=tenant, domain=f'{schema_name}.isolation-test.com', is_primary=True)
    return tenant


class TenantBoundJWTAuthenticationTests(TestCase):
    """Reproduce y verifica el cierre de la fuga cross-tenant vía JWT."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tenant_a = _crear_tenant('aislamiento_a')
        cls.tenant_b = _crear_tenant('aislamiento_b')

        from django.contrib.auth.models import User as TenantUser

        with schema_context(cls.tenant_a.schema_name):
            cls.user_a = TenantUser.objects.create_user(username='usuario_tenant_a', password='x')

    @classmethod
    def tearDownClass(cls):
        with schema_context('public'):
            cls.tenant_a.delete(force_drop=True)
            cls.tenant_b.delete(force_drop=True)
        super().tearDownClass()

    def _token_para_usuario_a(self):
        with schema_context(self.tenant_a.schema_name):
            token = AccessToken.for_user(self.user_a)
            token['schema_name'] = self.tenant_a.schema_name
            return token

    def test_token_del_tenant_a_no_autentica_en_tenant_b(self):
        """El hallazgo crítico: esto DEBE fallar. Antes del fix, no fallaba."""
        token = self._token_para_usuario_a()
        auth = TenantBoundJWTAuthentication()

        with schema_context(self.tenant_b.schema_name):
            with self.assertRaises(AuthenticationFailed):
                auth.get_user(token)

    def test_token_del_tenant_a_si_autentica_en_tenant_a(self):
        """El caso legítimo no debe romperse por el fix de seguridad."""
        token = self._token_para_usuario_a()
        auth = TenantBoundJWTAuthentication()

        with schema_context(self.tenant_a.schema_name):
            usuario = auth.get_user(token)
            self.assertEqual(usuario.pk, self.user_a.pk)

    def test_token_sin_schema_claim_solo_autentica_en_esquema_publico(self):
        """
        Tokens del esquema público (dueños de tenant, ver
        `backend.urls_public`) no llevan el claim `schema_name`. Deben
        seguir siendo válidos en 'public', pero no colarse en un tenant.
        """
        token = AccessToken.for_user(self.tenant_a.owner)
        auth = TenantBoundJWTAuthentication()

        with schema_context(self.tenant_a.schema_name):
            with self.assertRaises(AuthenticationFailed):
                auth.get_user(token)
