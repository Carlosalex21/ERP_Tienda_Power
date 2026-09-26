from django.db import migrations


def backfill_inventario_afectado(apps, schema_editor):
    """
    Facturas 'pagado'/'pendiente' con correlativo YA descontaron stock en su
    momento (ver `afectar_inventario_por_venta`, llamado sin condición desde
    siempre en `procesar_pago_factura_service`) -- sin este backfill, el
    default `False` del campo nuevo haría que anular una de estas facturas
    reales NO restaure su stock (el nuevo chequeo de idempotencia lo
    saltaría creyendo que nunca se descontó). Un 'borrador' nunca llegó a
    pagarse (nunca se descontó nada, `False` es correcto); una 'anulada' ya
    tuvo su stock restaurado por la anulación vieja (sin bandera), así que
    tampoco debe quedar en `True` -- eso significaría "todavía afectando
    stock", que ya no es cierto.
    """
    Factura = apps.get_model('facturacion', 'Factura')
    Factura.objects.filter(estado__in=['pagado', 'pendiente'], correlativo__isnull=False).update(
        inventario_afectado=True,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('facturacion', '0018_factura_inventario_afectado'),
    ]

    operations = [
        migrations.RunPython(backfill_inventario_afectado, noop),
    ]
