-- Області для Романа Ковальова та Павла Ковалишина (Supabase SQL Editor)

INSERT INTO manager_regions (manager_id, name)
SELECT u.id, r.name
FROM users u
CROSS JOIN (VALUES
    ('Дніпропетровська'),
    ('Полтавська'),
    ('Одеська'),
    ('Миколаївська'),
    ('Харківська'),
    ('Запорізька'),
    ('Кіровоградська')
) AS r(name)
WHERE u.telegram_id = 5009921383
ON CONFLICT (manager_id, name) DO NOTHING;

INSERT INTO manager_regions (manager_id, name)
SELECT u.id, r.name
FROM users u
CROSS JOIN (VALUES
    ('Вінницька'),
    ('Львівська'),
    ('Рівненська'),
    ('Волинська'),
    ('Тернопільська'),
    ('Чернівецька'),
    ('Хмельницька'),
    ('Закарпатська'),
    ('Івано-Франківська')
) AS r(name)
WHERE u.telegram_id = 7770797356
ON CONFLICT (manager_id, name) DO NOTHING;
