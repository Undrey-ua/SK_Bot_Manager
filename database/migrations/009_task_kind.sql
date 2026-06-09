-- Тип призначеної задачі (менеджерські задачі)

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS kind VARCHAR(32) NOT NULL DEFAULT 'general';

CREATE INDEX IF NOT EXISTS idx_tasks_kind ON tasks(kind);
