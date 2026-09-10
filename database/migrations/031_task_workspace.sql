-- Робочий простір задач: статуси канбану, пріоритет, клієнт, чек-лист, коментарі.

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS client_id BIGINT REFERENCES clients(id) ON DELETE SET NULL;
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'new';
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS priority VARCHAR(20) NOT NULL DEFAULT 'normal';
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS due_time VARCHAR(5);
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS add_to_calendar BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE tasks SET status = 'cancelled' WHERE deleted_at IS NOT NULL;
UPDATE tasks SET status = 'done' WHERE completed_at IS NOT NULL AND deleted_at IS NULL;
UPDATE tasks SET status = 'new'
WHERE completed_at IS NULL AND deleted_at IS NULL AND status NOT IN ('new', 'in_progress', 'waiting', 'done', 'cancelled');

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_client ON tasks(client_id);

CREATE TABLE IF NOT EXISTS task_checklist_items (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title VARCHAR(300) NOT NULL,
    is_done BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_task_checklist_task ON task_checklist_items(task_id);

CREATE TABLE IF NOT EXISTS task_comments (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id);

COMMENT ON COLUMN tasks.status IS 'new, in_progress, waiting, done, cancelled';
COMMENT ON COLUMN tasks.priority IS 'low, normal, high';
