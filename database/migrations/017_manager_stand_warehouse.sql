-- Віртуальний склад стендів регіонального менеджера

CREATE TABLE IF NOT EXISTS manager_stand_stock (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stand_id BIGINT NOT NULL REFERENCES stands(id) ON DELETE RESTRICT,
    quantity INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    UNIQUE (manager_id, stand_id)
);

CREATE INDEX IF NOT EXISTS idx_manager_stand_stock_manager ON manager_stand_stock(manager_id);
CREATE INDEX IF NOT EXISTS idx_manager_stand_stock_stand ON manager_stand_stock(stand_id);

ALTER TABLE stand_transfers
    ALTER COLUMN from_client_id DROP NOT NULL;

COMMENT ON TABLE manager_stand_stock IS 'Віртуальний склад стендів менеджера (не в аналітиці встановлених)';
COMMENT ON COLUMN stand_transfers.operation IS 'move, write_off, allocate, to_warehouse, from_warehouse';
