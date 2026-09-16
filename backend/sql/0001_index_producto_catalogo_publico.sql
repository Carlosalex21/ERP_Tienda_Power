-- Índice parcial para el catálogo público (apps.catalogo_publico): la
-- consulta siempre filtra por activo=true AND disponible_online=true, así
-- que un índice parcial cubre exactamente ese subconjunto sin indexar filas
-- que la consulta nunca toca.
CREATE INDEX IF NOT EXISTS idx_producto_catalogo_publico
    ON "Producto" (activo, disponible_online, categoria_id)
    WHERE activo = true AND disponible_online = true;
