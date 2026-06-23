-- Свотчі (нарізки зразків) на торговій точці без стенду. Продажі з них не в статистику стендів.

CREATE TABLE IF NOT EXISTS client_swatches (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    brand_id BIGINT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    UNIQUE (client_id, brand_id)
);

CREATE INDEX IF NOT EXISTS idx_client_swatches_client ON client_swatches(client_id);
CREATE INDEX IF NOT EXISTS idx_client_swatches_brand ON client_swatches(brand_id);

ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS from_swatch BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_sales_from_swatch ON sales(from_swatch) WHERE from_swatch = TRUE;

COMMENT ON TABLE client_swatches IS 'Нарізки зразків (свотчі) брендів на ТТ без стенду';
COMMENT ON COLUMN sales.from_swatch IS 'Продаж зі свотчу — не враховується в матриці/конверсії стендів';
