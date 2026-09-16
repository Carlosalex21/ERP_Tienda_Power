from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'sql'


def _read(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding='utf-8')


class Migration(migrations.Migration):
    """
    Aplica los scripts SQL versionados de `backend/sql/` relevantes para
    inventario. Ver `backend/sql/README.md` para la convención.
    """

    dependencies = [
        ('inventario', '0003_fase1_region_y_factura_electronica'),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read('0001_index_producto_catalogo_publico.sql'),
            reverse_sql=_read('0001_index_producto_catalogo_publico_reverse.sql'),
        ),
        migrations.RunSQL(
            sql=_read('0002_index_reservastock_valido_hasta.sql'),
            reverse_sql=_read('0002_index_reservastock_valido_hasta_reverse.sql'),
        ),
    ]
