-- Резерви (спільні) та задачі менеджерів

CREATE TABLE IF NOT EXISTS reserves (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    region_id BIGINT NOT NULL REFERENCES manager_regions(id),
    client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    material VARCHAR(200) NOT NULL,
    quantity NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    extended_count INT NOT NULL DEFAULT 0,
    cancelled_at TIMESTAMPTZ,
    expiry_notified_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reserves_expires_at ON reserves(expires_at);
CREATE INDEX IF NOT EXISTS idx_reserves_manager ON reserves(manager_id);
CREATE INDEX IF NOT EXISTS idx_reserves_client ON reserves(client_id);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    assignee_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_by_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(300) NOT NULL,
    comment TEXT,
    deadline DATE,
    weekday INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    reminder_sent_on DATE
);

CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
CREATE INDEX IF NOT EXISTS idx_tasks_weekday ON tasks(weekday);

