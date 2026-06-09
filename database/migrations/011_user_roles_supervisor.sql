-- Ролі: admin, leader (керівник), manager (регіональний), sales_manager (менеджер збуту)
-- sales_manager.supervisor_id → регіональний менеджер

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS supervisor_id BIGINT REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_users_supervisor ON users(supervisor_id);

COMMENT ON COLUMN users.supervisor_id IS 'Для role=sales_manager: id регіонального менеджера';
