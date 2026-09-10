-- Нотатки менеджера на робочий тиждень (понеділок).

CREATE TABLE IF NOT EXISTS task_week_notes (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (manager_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_task_week_notes_manager ON task_week_notes(manager_id, week_start);
