-- Швидші запити аналітики продажів
CREATE INDEX IF NOT EXISTS idx_sales_sold_at_manager ON sales (sold_at, manager_id);
CREATE INDEX IF NOT EXISTS idx_visits_manager_created ON visits (manager_id, created_at);
