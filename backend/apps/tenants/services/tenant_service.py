from django.db import transaction
from django.contrib.auth.models import User as PublicUser
from django.conf import settings
from django_tenants.utils import tenant_context

from apps.tenants.models import Client, Domain, Plan
from apps.tenants.services.subscription_service import SubscriptionService

class TenantCreationError(Exception):
    pass

class TenantService:
    @staticmethod
    @transaction.atomic
    def create_tenant(username, email, password, first_name, last_name, nombre_empresa, subdomain, tipo_negocio, plan_id=None, trial_days=14):
        """
        Maneja el registro completo y la creación de un nuevo inquilino.
        """
        # Nos aseguramos de que el dominio base no incluya el puerto para la comparación y guardado.
        base_domain_with_port = getattr(settings, 'TENANT_DOMAIN', 'localhost')
        base_domain = base_domain_with_port.split(':')[0]
        full_domain = f"{subdomain}.{base_domain}"

        # 1. Validaciones (se asume que el serializer ya las hizo, pero una doble verificación no está de más)
        if Domain.objects.filter(domain=full_domain).exists():
            raise TenantCreationError(f"El subdominio '{subdomain}' ya está en uso.")
        if PublicUser.objects.filter(username__iexact=username).exists():
            raise TenantCreationError(f"El nombre de usuario '{username}' ya está en uso.")
        if PublicUser.objects.filter(email__iexact=email).exists():
            raise TenantCreationError(f"El correo electrónico '{email}' ya está registrado.")
        
        # 2. Crear el usuario público (dueño)
        owner = PublicUser.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name
        )

        # 3. Crear el Client (Tenant), lo que dispara la creación del esquema
        tenant = Client.objects.create(
            owner=owner,
            nombre_empresa=nombre_empresa,
            email_contacto=email,
            schema_name=subdomain,
            tipo_negocio=tipo_negocio
        )

        # 4. Crear el Dominio
        Domain.objects.create(domain=full_domain, tenant=tenant, is_primary=True)

        # 5. Crear la Suscripción (Prueba o Pagada)
        if plan_id:
            plan = Plan.objects.get(id=plan_id)
            # En un futuro, aquí se integraría con la pasarela de pago antes de continuar.
            SubscriptionService.create_subscription(client_id=tenant.id, plan_id=plan.id)
        else:
            # Por defecto, se crea o usa un plan de prueba.
            trial_plan, _ = Plan.objects.get_or_create(
                nombre="Plan de Prueba",
                defaults={
                    'precio': 0.00, 'limite_usuarios': 2, 'limite_sucursales': 1,
                    'descripcion': 'Plan de prueba gratuito por tiempo limitado.'
                }
            )
            SubscriptionService.create_subscription(client_id=tenant.id, plan_id=trial_plan.id, duration_days=trial_days)

        # 6. Crear el primer usuario *dentro* del esquema del nuevo inquilino
        with tenant_context(tenant):
            from django.contrib.auth.models import User as TenantUser
            from apps.usuarios.models import UserMetadata, Rol

            admin_rol, _ = Rol.objects.get_or_create(nombre="Administrador")
            tenant_user = TenantUser.objects.create_user(
                username=username, email=email, password=password,
                first_name=first_name, last_name=last_name,
                is_superuser=True, is_staff=True
            )
            UserMetadata.objects.create(user=tenant_user, rol=admin_rol)

        return tenant