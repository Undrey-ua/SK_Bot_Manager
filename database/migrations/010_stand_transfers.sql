-- Історія переміщень стендів між торговими точками

CREATE TABLE IF NOT EXISTS stand_transfers (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    to_client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    stand_id BIGINT NOT NULL REFERENCES stands(id) ON DELETE RESTRICT,
    quantity INT NOT NULL DEFAULT 1 CHECK (quantity >= 1),
    to_was_new BOOLEAN NOT NULL DEFAULT FALSE,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stand_transfers_manager ON stand_transfers(manager_id);
CREATE INDEX IF NOT EXISTS idx_stand_transfers_created ON stand_transfers(created_at);
CREATE INDEX IF NOT EXISTS idx_stand_transfers_stand ON stand_transfers(stand_id);
CREATE INDEX IF NOT EXISTS idx_stand_transfers_from ON stand_transfers(from_client_id);
CREATE INDEX IF NOT EXISTS idx_stand_transfers_to ON stand_transfers(to_client_id);
