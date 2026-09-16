from django.db import migrations, models


class Migration(migrations.Migration):
    """
    ``MovimientoInventario.cantidad`` era una FK a ``Producto`` en lugar de
    la cantidad numérica movida (bug de modelado detectado en la auditoría:
    los servicios de stock nunca podían registrar cuánto se movió). Se
    renombra a ``producto`` -- que es lo que en realidad representaba -- y
    se agrega el campo entero que faltaba.
    """

    dependencies = [
        ('inventario', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='movimientoinventario',
            old_name='cantidad',
            new_name='producto',
        ),
        migrations.AddField(
            model_name='movimientoinventario',
            name='cantidad_movida',
            field=models.IntegerField(default=0),
        ),
    ]
