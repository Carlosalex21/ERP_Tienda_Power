"""
Base de tests multi-tenant del proyecto.

``django_tenants.test.cases.TenantTestCase`` crea el tenant de prueba sin
completar los campos propios del proyecto que son obligatorios
(``Client.owner``). La librería expone ``setup_tenant()`` exactamente para
este caso (ver su docstring: "required if you have required fields") --
aquí se asigna un owner de prueba antes de guardar el tenant.

Sin esto, cualquier test que herede de ``TenantTestCase`` directamente falla
en ``setUpClass`` con ``IntegrityError: null value in column "owner_id"``
en cuanto ``Client.owner`` es NOT NULL (ver migración
``apps.tenants.migrations.0005_remove_plan_stripe_price_id_and_more``).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase


class BaseTenantTestCase(TenantTestCase):
    """``TenantTestCase`` que además satisface los campos obligatorios del proyecto."""

    @classmethod
    def setup_tenant(cls, tenant):
        super().setup_tenant(tenant)
        user_model = get_user_model()
        owner, _ = user_model.objects.get_or_create(
            username="tenant-test-owner",
            defaults={"email": "tenant-test-owner@example.com"},
        )
        tenant.owner = owner
