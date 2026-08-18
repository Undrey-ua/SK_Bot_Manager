-- Сфера роботи регіонального менеджера та окрема база клієнтів ПВХ.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS work_scope VARCHAR(20) NOT NULL DEFAULT 'stand';

COMMENT ON COLUMN users.work_scope IS 'stand | pvc | both';

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS is_pvc BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_clients_is_pvc ON clients (is_pvc);

-- Андрій Вовнянко — стенди і ПВХ
UPDATE users
SET work_scope = 'both'
WHERE telegram_id = 535827585;
