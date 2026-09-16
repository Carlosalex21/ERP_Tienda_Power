from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'sql'


def _read(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding='utf-8')


class Migration(migrations.Migration):
    """
    Aplica los scripts SQL versionados de `backend/sql/` relevantes para
    facturación. Ver `backend/sql/README.md` para la convención.
    """

    dependencies = [
        ('facturacion', '0006_fase1_region_y_factura_electronica'),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read('0003_index_factura_fecha_moneda.sql'),
            reverse_sql=_read('0003_index_factura_fecha_moneda_reverse.sql'),
        ),
    ]
