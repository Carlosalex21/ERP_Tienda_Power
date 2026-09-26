from django.db import migrations


def bootstrap_inventario(apps, schema_editor):
    """
    `Inventario` (el desglose de stock POR ALMACÉN) nunca se mantuvo
    actualizado -- todo el stock real vivía únicamente en `Producto.cantidad`
    (un solo número global, sin importar en qué almacén está físicamente).
    Antes de que el traslado entre almacenes tenga sentido, hace falta un
    punto de partida real: esta migración asigna el stock actual de cada
    producto al almacén que ya tenía asignado (`Producto.almacen`), o al
    primer almacén activo del tenant si no tenía ninguno (creando un
    "Almacén Principal" si el tenant no tiene NINGÚN almacén todavía). El
    total global (`Producto.cantidad`) no se toca -- esta migración solo
    reparte ESE MISMO número en el desglose por almacén.
    """
    Producto = apps.get_model('inventario', 'Producto')
    Almacen = apps.get_model('inventario', 'Almacen')
    Inventario = apps.get_model('inventario', 'Inventario')

    productos_con_stock = Producto.objects.filter(cantidad__gt=0)
    if not productos_con_stock.exists():
        return

    almacen_default = None

    for producto in productos_con_stock:
        almacen = producto.almacen
        if almacen is None:
            if almacen_default is None:
                almacen_default = Almacen.objects.filter(activo=True).order_by('id').first()
            if almacen_default is None:
                almacen_default = Almacen.objects.create(
                    nombre='Almacén Principal',
                    direccion='',
                    activo=True,
                )
            almacen = almacen_default

        Inventario.objects.update_or_create(
            producto=producto, almacen=almacen,
            defaults={'cantidad': producto.cantidad, 'activo': True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0014_trasladoinventario_trasladoinventariodetalle'),
    ]

    operations = [
        migrations.RunPython(bootstrap_inventario, noop),
    ]
