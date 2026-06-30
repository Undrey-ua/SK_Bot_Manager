-- Дворівневий склад: центральний пул + квота менеджера на центральному

CREATE TABLE IF NOT EXISTS central_stand_stock (
    id BIGSERIAL PRIMARY KEY,
    stand_id BIGINT NOT NULL UNIQUE REFERENCES stands(id) ON DELETE RESTRICT,
    quantity INT NOT NULL DEFAULT 0 CHECK (quantity >= 0)
);

CREATE INDEX IF NOT EXISTS idx_central_stand_stock_stand ON central_stand_stock(stand_id);

CREATE TABLE IF NOT EXISTS manager_central_allocation (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stand_id BIGINT NOT NULL REFERENCES stands(id) ON DELETE RESTRICT,
    quantity INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    UNIQUE (manager_id, stand_id)
);

CREATE INDEX IF NOT EXISTS idx_manager_central_allocation_manager ON manager_central_allocation(manager_id);
CREATE INDEX IF NOT EXISTS idx_manager_central_allocation_stand ON manager_central_allocation(stand_id);

COMMENT ON TABLE central_stand_stock IS 'Нерозподілений залишок стендів на центральному складі';
COMMENT ON TABLE manager_central_allocation IS 'Квота менеджера на центральному складі (read-only для менеджера)';
