-- План продажів (кв. м) на місяць для кожного менеджера
CREATE TABLE IF NOT EXISTS manager_sales_plans (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    year INT NOT NULL,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    target_sqm NUMERIC(12, 2) NOT NULL,
    created_by_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (manager_id, year, month)
);

CREATE INDEX IF NOT EXISTS idx_manager_sales_plans_period
    ON manager_sales_plans (year, month);
