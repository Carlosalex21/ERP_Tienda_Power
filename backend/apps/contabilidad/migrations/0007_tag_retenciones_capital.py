from django.db import migrations


def taguear_cuentas(apps, schema_editor):
    """
    Retro-etiqueta las cuentas sembradas antes de que existieran estos roles
    (mismo criterio que 0005): sin esto, el asiento de una retención a
    proveedor y el de un inventario inicial no encuentran su cuenta.
    """
    CuentaContable = apps.get_model('contabilidad', 'CuentaContable')
    CuentaContable.objects.filter(codigo='2.1.03', rol__isnull=True).update(rol='retenciones_pagar')
    CuentaContable.objects.filter(codigo='3.1', rol__isnull=True).update(rol='capital')


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0006_alter_asientocontable_origen_and_more'),
    ]

    operations = [
        migrations.RunPython(taguear_cuentas, migrations.RunPython.noop),
    ]
