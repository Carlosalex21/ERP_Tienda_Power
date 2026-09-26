from django.db import migrations


def taguear_cuenta_sueldos(apps, schema_editor):
    """
    Retro-etiqueta con rol='gasto_sueldos' la cuenta '6.1.01' (Sueldos y
    Salarios) de cualquier `EmpresaContable` que ya existiera ANTES de que
    ese rol se agregara al `PLAN_CUENTAS_DEFAULT` -- sin esto, el asiento
    automático de nómina (`generar_asiento_automatico_nomina`) nunca
    encuentra la cuenta y no genera nada para empresas ya sembradas.
    """
    CuentaContable = apps.get_model('contabilidad', 'CuentaContable')
    CuentaContable.objects.filter(codigo='6.1.01', rol__isnull=True).update(rol='gasto_sueldos')


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0004_alter_asientocontable_origen_and_more'),
    ]

    operations = [
        migrations.RunPython(taguear_cuenta_sueldos, migrations.RunPython.noop),
    ]
