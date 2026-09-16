-- Acelera reportes/consolidación multi-moneda (apps.reportes): las
-- consultas de reportes filtran/agrupan casi siempre por rango de fecha y
-- por moneda de la operación.
CREATE INDEX IF NOT EXISTS idx_factura_fecha_moneda
    ON "Factura" (fecha_operacion, moneda_id);
