-- Додаткові індекси для списків і фільтрів
CREATE INDEX IF NOT EXISTS idx_visits_created_at ON visits (created_at);
CREATE INDEX IF NOT EXISTS idx_clients_region_id ON clients (region_id);
CREATE INDEX IF NOT EXISTS idx_clients_city ON clients (city) WHERE city IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_assignee_active
  ON tasks (assignee_id, deadline)
  WHERE deleted_at IS NULL AND completed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_reserves_active_expires
  ON reserves (expires_at)
  WHERE cancelled_at IS NULL;
