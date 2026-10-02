from django.db import migrations


def agregar_facturas_compra(apps, schema_editor):
    """
    El módulo "facturas_compra" es nuevo: los planes con lista explícita de
    módulos que ya vendían Proveedores (antes las compras se cargaban por
    Ajustes) lo reciben, para que nadie pierda la forma de registrar compras.
    Los planes con lista vacía ya incluyen todo.
    """
    Plan = apps.get_model('tenants', 'Plan')
    for plan in Plan.objects.exclude(modulos=[]):
        modulos = list(plan.modulos or [])
        if 'facturas_compra' in modulos:
            continue
        if 'proveedores' in modulos or 'ordenes_compra' in modulos or 'ajustes_inventario' in modulos:
            modulos.append('facturas_compra')
            plan.modulos = modulos
            plan.save(update_fields=['modulos'])


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0018_subscriptionpayment_credito_aplicado'),
    ]

    operations = [
        migrations.RunPython(agregar_facturas_compra, migrations.RunPython.noop),
    ]
