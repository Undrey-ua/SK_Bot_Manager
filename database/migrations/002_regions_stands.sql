-- Міграція для існуючої БД. Виконайте в Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS manager_regions (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    UNIQUE (manager_id, name)
);

CREATE TABLE IF NOT EXISTS stands (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS client_stands (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    stand_id BIGINT NOT NULL REFERENCES stands(id) ON DELETE CASCADE,
    UNIQUE (client_id, stand_id)
);

-- Нові колонки clients (якщо таблиця вже існує)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS region_id BIGINT REFERENCES manager_regions(id);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS comment TEXT;

-- Початкові стенди
INSERT INTO stands (name, sort_order) VALUES
    ('BIG', 1),
    ('BerryAlloc: Smartline', 2),
    ('IVC: Solida', 3),
    ('ADO', 4),
    ('Prisma', 5),
    ('Tarkett SPC', 6)
ON CONFLICT (name) DO NOTHING;

-- Після міграції даних видаліть старі колонки вручну (опційно):
-- ALTER TABLE clients DROP COLUMN IF EXISTS type;
-- ALTER TABLE clients DROP COLUMN IF EXISTS district;
