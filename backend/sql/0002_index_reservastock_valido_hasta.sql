-- Acelera el job de limpieza de reservas de stock expiradas (Fase 2:
-- separación de stock disponible vs. reservado) -- ese job siempre filtra
-- por valido_hasta.
CREATE INDEX IF NOT EXISTS idx_reservastock_valido_hasta
    ON "ReservaStock" (valido_hasta);
