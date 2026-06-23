-- Позначка продажу з резерву (закриває резерв без скасування).

ALTER TABLE reserves
    ADD COLUMN IF NOT EXISTS sold_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_reserves_sold_at ON reserves(sold_at) WHERE sold_at IS NOT NULL;

COMMENT ON COLUMN reserves.sold_at IS 'Час продажу з резерву — резерв більше не активний';
