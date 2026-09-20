from django.conf import settings
from django.db import migrations


def seed_configured_domain(apps, schema_editor):
    """
    Registra `settings.TENANT_DOMAIN` como Domain del esquema público.

    La migración 0003 solo sembró 'localhost'/'127.0.0.1' (fijos, para
    desarrollo) -- en cualquier despliegue con un dominio real,
    django-tenants no encontraba NINGÚN tenant para ese Host y devolvía 404
    en TODO el esquema público (registro, login, `/admin/tenants/plans/`,
    etc.), incluso con el backend funcionando perfectamente bien. Con esto,
    cualquier despliegue nuevo (o reinstalación) sigue funcionando sin un
    paso manual aparte -- basta con tener `TENANT_DOMAIN` bien puesto en el
    entorno antes de migrar.
    """
    Client = apps.get_model('tenants', 'Client')
    Domain = apps.get_model('tenants', 'Domain')

    dominio_configurado = getattr(settings, 'TENANT_DOMAIN', 'localhost:8000').split(':')[0]
    if not dominio_configurado or dominio_configurado in ('localhost', '127.0.0.1'):
        # Ya cubierto por la migración 0003 -- nada que hacer (evita un
        # get_or_create redundante en cada entorno de desarrollo).
        return

    public, _ = Client.objects.get_or_create(
        schema_name='public',
        defaults={
            'nombre_empresa': 'Administración SaaS',
            'email_contacto': 'admin@power.com',
            'esta_activo': True,
        },
    )
    Domain.objects.get_or_create(
        domain=dominio_configurado,
        tenant=public,
        defaults={'is_primary': True},
    )


def noop_reverse(apps, schema_editor):
    """No se revierte: quitar el dominio de producción rompería el sitio en caliente."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0011_subscriptionpayment_periodo'),
    ]

    operations = [
        migrations.RunPython(seed_configured_domain, noop_reverse),
    ]
