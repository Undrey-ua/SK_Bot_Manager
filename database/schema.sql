-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'manager',
    supervisor_id BIGINT REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100),
    district VARCHAR(100),
    address VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS visits (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    visit_type VARCHAR(50) NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS visit_tasks (
    id BIGSERIAL PRIMARY KEY,
    visit_id BIGINT NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
    task VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS visit_photos (
    id BIGSERIAL PRIMARY KEY,
    visit_id BIGINT NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
    photo_url VARCHAR(1000) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_manager ON clients(manager_id);
CREATE INDEX IF NOT EXISTS idx_visits_manager ON visits(manager_id);
CREATE INDEX IF NOT EXISTS idx_visits_client ON visits(client_id);

-- Example manager (replace telegram_id with real value)
-- INSERT INTO users (telegram_id, name, role) VALUES (123456789, 'Іван Петренко', 'manager');
-- INSERT INTO clients (manager_id, name, type, district, address)
-- VALUES (1, 'Магазин Центр', 'retail', 'Київ', 'вул. Хрещатик, 1');
