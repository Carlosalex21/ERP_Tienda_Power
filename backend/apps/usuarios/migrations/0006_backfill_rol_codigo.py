from django.db import migrations

_NOMBRE_A_CODIGO = {
    "administrador": "admin",
    "vendedor": "vendedor",
    "cajero": "cajero",
    "almacenista": "almacenista",
    "rrhh": "rrhh",
}


def backfill_codigo(apps, schema_editor):
    """Asigna `codigo` a los roles sembrados con los nombres estándar."""
    Rol = apps.get_model("usuarios", "Rol")
    for rol in Rol.objects.filter(codigo__isnull=True):
        codigo = _NOMBRE_A_CODIGO.get((rol.nombre or "").strip().lower())
        if codigo:
            rol.codigo = codigo
            rol.save(update_fields=["codigo"])


def noop_reverse(apps, schema_editor):
    """No hay nada que revertir: dejar `codigo` en null es un estado válido."""


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0005_fase1_pais_y_rol_codigo'),
    ]

    operations = [
        migrations.RunPython(backfill_codigo, noop_reverse),
    ]
