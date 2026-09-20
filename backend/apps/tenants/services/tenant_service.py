"""
Servicio de aprovisionamiento automático de inquilinos (tenants).

Crea el esquema del tenant, su dominio, la suscripción, el usuario
administrador y **siembra los datos mínimos** para que el inquilino pueda
operar de inmediato: roles, configuraciones de IVA/IGV (según el país
elegido en el registro), configuración de empresa, moneda base, almacén
principal y correlativo.
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


# Moneda base por país. El IVA/impuestos se derivan dinámicamente de
# ``TaxStrategyRegistry`` (ver abajo); la moneda no forma parte de esa
# estrategia y se mantiene como un mapa simple aquí.
_MONEDA_BASE_POR_PAIS = {
    "VE": {"codigo": "VES", "nombre": "Bolívar Soberano", "simbolo": "Bs."},
    "CO": {"codigo": "COP", "nombre": "Peso Colombiano", "simbolo": "$"},
    "PE": {"codigo": "PEN", "nombre": "Sol Peruano", "simbolo": "S/"},
}


def _seed_tenant_defaults(
    tenant: Client,
    owner_username: str,
    owner_email: str,
    password: str,
    first_name: str,
    last_name: str,
    nombre_empresa: str,
    pais_codigo: str,
    tipo_negocio: str = 'retail',
    cantidad_mesas: int = 6,
) -> None:
    """
    Siembra los datos mínimos dentro del esquema del tenant.

    Se ejecuta dentro de ``tenant_context(tenant)`` y es inmune a
    duplicados mediante ``get_or_create``.
    """
    from django.contrib.auth.models import User as TenantUser

    from apps.usuarios.models import Rol, UserMetadata
    from apps.configuracion.core.tax_strategy import TaxStrategyRegistry
    from apps.configuracion.models import (
        ConfiguracionCorrelativo,
        ConfiguracionEmpresa,
        Configuracioniva,
        Moneda,
        TasaCambio,
    )
    from apps.inventario.models import Almacen

    # 1. Roles base del sistema (código estable + nombre visible).
    roles = [
        ("admin", "Administrador"),
        ("vendedor", "Vendedor"),
        ("cajero", "Cajero"),
        ("almacenista", "Almacenista"),
        ("rrhh", "RRHH"),
    ]
    for codigo, rol_nombre in roles:
        Rol.objects.get_or_create(nombre=rol_nombre, defaults={"codigo": codigo})

    # 2. Usuario administrador + perfil.
    admin_rol, _ = Rol.objects.get_or_create(nombre="Administrador", defaults={"codigo": "admin"})

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

    # 3. Configuración de empresa (pk=1), con el país elegido en el registro.
    ConfiguracionEmpresa.objects.get_or_create(
        pk=1,
        defaults={
            "nombre_comercial": nombre_empresa,
            "razon_social": nombre_empresa,
            "pais_codigo": pais_codigo,
        },
    )

    # 4. Almacén principal por defecto.
    Almacen.objects.get_or_create(
        nombre="Almacén Principal",
        defaults={"direccion": "Dirección por configurar"},
    )

    # 5. Configuraciones de IVA/IGV según el país elegido, derivadas de la
    # misma TaxStrategy que usa el motor de facturación (una sola fuente de
    # verdad para las tasas: no se hardcodean aquí).
    strategy = TaxStrategyRegistry(pais_codigo).get_strategy()
    for tasa_info in strategy.get_tax_rates():
        Configuracioniva.objects.get_or_create(
            nombre=str(tasa_info["name"]),
            defaults={"porcentaje_iva": Decimal(str(tasa_info["rate"])), "activo": True},
        )

    # 6. Monedas: la moneda base del país como predeterminada, USD secundaria
    # (economías dolarizadas de facto: útil también para CO/PE).
    moneda_base_info = _MONEDA_BASE_POR_PAIS.get(pais_codigo, _MONEDA_BASE_POR_PAIS["VE"])
    moneda_base, moneda_base_created = Moneda.objects.get_or_create(
        codigo=moneda_base_info["codigo"],
        defaults={
            "nombre": moneda_base_info["nombre"],
            "simbolo": moneda_base_info["simbolo"],
            "es_predeterminada": True,
        },
    )
    if moneda_base_created:
        TasaCambio.objects.create(moneda=moneda_base, tasa=Decimal("1.000000"), fuente="Sistema")
    if moneda_base_info["codigo"] != "USD":
        Moneda.objects.get_or_create(
            codigo="USD",
            defaults={"nombre": "Dólar Estadounidense", "simbolo": "$", "es_predeterminada": False},
        )

    # 7. Correlativo de facturación por defecto.
    ConfiguracionCorrelativo.objects.get_or_create(
        pk=1,
        defaults={"prefijo": "F-", "current_number": 0, "number_length": 3},
    )

    # 8. Mesas para un tenant de restaurante -- la cantidad la indica el
    # propio dueño en el registro (cada local tiene un número distinto de
    # mesas); se siembran ya numeradas para que el módulo no arranque vacío,
    # pero puede agregar/quitar/renombrar mesas después desde el panel.
    if tipo_negocio == 'restaurante':
        from apps.restaurantes.models import Mesa

        for numero in range(1, max(1, cantidad_mesas) + 1):
            Mesa.objects.get_or_create(numero=f"Mesa {numero}")


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
        pais_codigo: str = "VE",
        plan_id: int | None = None,
        trial_days: int = 14,
        cantidad_mesas: int = 6,
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
            tipo_negocio: 'retail' | 'b2b' | 'restaurante' | 'farmacia' | 'servicios'.
            pais_codigo: País de operación ('VE' | 'CO' | 'PE'), elegido como
                primer paso del registro. Condiciona la moneda base y las
                tasas de IVA/IGV sembradas para el tenant.
            plan_id: ID de plan opcional.
            trial_days: Días de prueba cuando no se provee plan.
            cantidad_mesas: Solo aplica si tipo_negocio='restaurante' -- cantidad
                de mesas que el dueño indicó tener, sembradas de una vez.

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
            pais_codigo=pais_codigo,
        )

        # Dominio primario.
        Domain.objects.create(domain=full_domain, tenant=tenant, is_primary=True)

        # Toda alta nueva arranca SIEMPRE con el plan de prueba, sin importar
        # qué plan de pago haya elegido el usuario en el registro. Activar un
        # plan de pago sin cobrarlo era el hueco de seguridad que permitía
        # obtener cualquier plan gratis: la activación real del plan pagado
        # ocurre después, cuando `SubscriptionPaymentService.confirmar_pago`
        # confirma un pago real (Pago Móvil/Zelle manual o Stripe). `plan_id`
        # se conserva solo para validar que el plan elegido existe.
        if plan_id and not Plan.objects.filter(id=plan_id).exists():
            raise TenantCreationError(f"El plan seleccionado (id={plan_id}) no existe.")

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
                pais_codigo=pais_codigo,
                tipo_negocio=tipo_negocio,
                cantidad_mesas=cantidad_mesas,
            )

        logger.info("Tenant %s creado y aprovisionado.", tenant.schema_name)
        return tenant
