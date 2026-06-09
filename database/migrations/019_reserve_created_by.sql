-- Хто створив резерв (керівник від імені менеджера тощо)
ALTER TABLE reserves
    ADD COLUMN IF NOT EXISTS created_by_id BIGINT REFERENCES users(id) ON DELETE SET NULL;

UPDATE reserves SET created_by_id = manager_id WHERE created_by_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_reserves_created_by ON reserves(created_by_id);
