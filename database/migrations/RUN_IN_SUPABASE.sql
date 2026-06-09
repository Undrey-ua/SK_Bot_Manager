-- Скопіюйте ВЕСЬ цей файл у Supabase → SQL Editor → Run (один раз)

-- 1. Нові таблиці
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

-- 2. Нові поля в clients
ALTER TABLE clients ADD COLUMN IF NOT EXISTS region_id BIGINT REFERENCES manager_regions(id);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS comment TEXT;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS address VARCHAR(500);
UPDATE clients SET address = '' WHERE address IS NULL;

-- 3. Каталог стендів
INSERT INTO stands (name, sort_order, is_active) VALUES
    ('BIG', 1, TRUE),
    ('BerryAlloc: Smartline', 2, TRUE),
    ('IVC: Solida', 3, TRUE),
    ('ADO', 4, TRUE),
    ('Prisma', 5, TRUE),
    ('Tarkett SPC', 6, TRUE)
ON CONFLICT (name) DO UPDATE SET is_active = TRUE;

-- 4. Області для існуючих клієнтів (з поля district, якщо було)
INSERT INTO manager_regions (manager_id, name)
SELECT DISTINCT manager_id, COALESCE(NULLIF(TRIM(district), ''), 'Загальна')
FROM clients
WHERE region_id IS NULL
ON CONFLICT (manager_id, name) DO NOTHING;

UPDATE clients c
SET region_id = mr.id
FROM manager_regions mr
WHERE c.region_id IS NULL
  AND c.manager_id = mr.manager_id
  AND mr.name = COALESCE(NULLIF(TRIM(c.district), ''), 'Загальна');
