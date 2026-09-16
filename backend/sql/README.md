# `backend/sql/`

Scripts SQL versionados (índices, vistas, ajustes de rendimiento) que no
tienen representación directa como campo de modelo de Django.

## Convención

- Un archivo `.sql` por cambio, numerado y con un nombre que diga qué hace:
  `0004_index_nombre_de_la_tabla.sql`.
- Si el cambio necesita revertirse, un segundo archivo `..._reverse.sql`.
- Cada script se aplica desde una migración normal de Django, vía
  `migrations.RunSQL(sql=..., reverse_sql=...)`, leyendo el archivo con
  `Path(__file__).resolve().parent.parent.parent / 'sql' / 'archivo.sql'`.
  Así `migrate_schemas --tenant` lo aplica automáticamente a todos los
  esquemas de tenant, igual que cualquier otra migración.
- Usar siempre `CREATE INDEX IF NOT EXISTS` / `DROP INDEX IF EXISTS` (u
  operaciones igualmente idempotentes): la migración puede reintentarse o
  aplicarse a un esquema que ya tenía el índice creado manualmente.
- Los nombres de tabla usan mayúsculas exactas entre comillas dobles
  (`"Producto"`, `"Factura"`, `"ReservaStock"`) porque los modelos definen
  `Meta.db_table` con mayúsculas -- Postgres solo respeta el case si el
  identificador va entre comillas.

Ver `apps/inventario/migrations/0004_sql_indices.py` y
`apps/facturacion/migrations/0007_sql_index_factura.py` para el patrón de
referencia.
