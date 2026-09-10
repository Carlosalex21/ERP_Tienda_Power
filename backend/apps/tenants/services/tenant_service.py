"""
Servicio de aprovisionamiento automático de inquilinos (tenants).

Crea el esquema del tenant, su dominio, la suscripción, el usuario
administrador y **siembra los datos mínimos** para que el inquilino pueda
operar de inmediato: roles, configuraciones de IVA (SENIAT), configuración
de empresa, moneda base, almacén principal y correlativo.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User as PublicUser
from django.db import transaction
from django_tenants.utils import tenant_context

from apps.tenants.models import Client, Domain, Plan
from apps.tenants.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class TenantCreationError(Exception):
    """Error controlado durante la creación de un inquilino."""


def _seed_tenant_defaults(
    tenant: Client,
    owner_username: str,
    owner_email: str,
    password: str,
    first_name: str,
    last_name: str,
    nombre_empresa: str,
) -> None:
    """
    Siembra los datos mínimos dentro del esquema del tenant.

    Se ejecuta dentro de ``tenant_context(tenant)`` y es inmune a
    duplicados mediante ``get_or_create``.
    """
    from django.contrib.auth.models import User as TenantUser

    from apps.usuarios.models import Rol, UserMetadata
    from apps.configuracion.models import (
        ConfiguracionCorrelativo,
        ConfiguracionEmpresa,
        Configuracioniva,
        Moneda,
        TasaCambio,
    )
    from apps.inventario.models import Almacen

    # 1. Roles base del sistema.
    roles = ["Administrador", "Vendedor", "Cajero", "Almacenista", "RRHH"]
    for rol_nombre in roles:
        Rol.objects.get_or_create(nombre=rol_nombre)

    # 2. Usuario administrador + perfil.
    admin_rol, _ = Rol.objects.get_or_create(nombre="Administrador")
    
    tenant_user, created = TenantUser.objects.update_or_create(
        username=owner_username,
        defaults={
            "email": owner_email,
            "first_name": first_name,
            "last_name": last_name,
            "is_superuser": True,
            "is_staff": True,
            "is_active": True,
        },
    )
    # Siempre actualizamos la contraseña para garantizar que el hash coincida con el texto plano recibido
    tenant_user.set_password(password)
    tenant_user.save()
    UserMetadata.objects.get_or_create(user=tenant_user, defaults={"rol": admin_rol})

    # 3. Configuración de empresa (pk=1).
    ConfiguracionEmpresa.objects.get_or_create(
        pk=1,
        defaults={"nombre_comercial": nombre_empresa, "razon_social": nombre_empresa},
    )

    # 4. Almacén principal por defecto.
    Almacen.objects.get_or_create(
        nombre="Almacén Principal",
        defaults={"direccion": "Dirección por configurar"},
    )

    # 5. Configuraciones de IVA (SENIAT: 16 %, 8 %, exento).
    Configuracioniva.objects.get_or_create(
        nombre="IVA General",
        defaults={"porcentaje_iva": Decimal("16.00"), "activo": True},
    )
    Configuracioniva.objects.get_or_create(
        nombre="IVA Reducido",
        defaults={"porcentaje_iva": Decimal("8.00"), "activo": True},
    )
    Configuracioniva.objects.get_or_create(
        nombre="Exento",
        defaults={"porcentaje_iva": Decimal("0.00"), "activo": True},
    )

    # 6. Monedas: VES como base, USD secundaria.
    ves, ves_created = Moneda.objects.get_or_create(
        codigo="VES",
        defaults={"nombre": "Bolívar Soberano", "simbolo": "Bs.", "es_predeterminada": True},
    )
    if ves_created:
        TasaCambio.objects.create(moneda=ves, tasa=Decimal("1.000000"), fuente="Sistema")
    Moneda.objects.get_or_create(
        codigo="USD",
        defaults={"nombre": "Dólar Estadounidense", "simbolo": "$", "es_predeterminada": False},
    )

    # 7. Correlativo de facturación por defecto.
    ConfiguracionCorrelativo.objects.get_or_create(
        pk=1,
        defaults={"prefijo": "F-", "current_number": 0, "number_length": 3},
    )


class TenantService:
    """Crea y aprovisiona inquilinos de forma atómica."""

    @staticmethod
    @transaction.atomic
    def create_tenant(
        username: str,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        nombre_empresa: str,
        subdomain: str,
        tipo_negocio: str,
        plan_id: int | None = None,
        trial_days: int = 14,
    ) -> Client:
        """
        Registra un nuevo inquilino completo.

        Args:
            username: Nombre de usuario del dueño.
            email: Correo del dueño.
            password: Contraseña.
            first_name: Nombre de pila.
            last_name: Apellido.
            nombre_empresa: Nombre de la empresa.
            subdomain: Subdominio único (schema_name y dominio).
            tipo_negocio: 'retail' | 'b2b'.
            plan_id: ID de plan opcional.
            trial_days: Días de prueba cuando no se provee plan.

        Returns:
            Client: El inquilino creado y aprovisionado.

        Raises:
            TenantCreationError: Si el subdominio o las credenciales ya existen.
        """
        base_domain_with_port = getattr(settings, "TENANT_DOMAIN", "localhost")
        base_domain = base_domain_with_port.split(":")[0]
        full_domain = f"{subdomain}.{base_domain}"

        # Validaciones previas.
        if Domain.objects.filter(domain=full_domain).exists():
            raise TenantCreationError(f"El subdominio '{subdomain}' ya está en uso.")
        if PublicUser.objects.filter(username__iexact=username).exists():
            raise TenantCreationError(f"El nombre de usuario '{username}' ya está en uso.")
        if PublicUser.objects.filter(email__iexact=email).exists():
            raise TenantCreationError(f"El correo electrónico '{email}' ya está registrado.")

        # Usuario público dueño.
        owner = PublicUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        # Tenant (dispara la creación del esquema por auto_create_schema).
        tenant = Client.objects.create(
            owner=owner,
            nombre_empresa=nombre_empresa,
            email_contacto=email,
            schema_name=subdomain,
            tipo_negocio=tipo_negocio,
        )

        # Dominio primario.
        Domain.objects.create(domain=full_domain, tenant=tenant, is_primary=True)

        # Suscripción (plan explícito o plan de prueba).
        if plan_id:
            plan = Plan.objects.get(id=plan_id)
            SubscriptionService.create_subscription(client_id=tenant.id, plan_id=plan.id)
        else:
            trial_plan, _ = Plan.objects.get_or_create(
                nombre="Plan de Prueba",
                defaults={
                    "precio": Decimal("0.00"),
                    "limite_usuarios": 2,
                    "limite_sucursales": 1,
                    "descripcion": "Plan de prueba gratuito por tiempo limitado.",
                },
            )
            SubscriptionService.create_subscription(
                client_id=tenant.id, plan_id=trial_plan.id, duration_days=trial_days
            )

        # Siembra de datos mínimos dentro del esquema del tenant.
        with tenant_context(tenant):
            _seed_tenant_defaults(
                tenant=tenant,
                owner_username=username,
                owner_email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                nombre_empresa=nombre_empresa,
            )

        logger.info("Tenant %s creado y aprovisionado.", tenant.schema_name)
        return tenant
