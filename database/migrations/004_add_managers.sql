-- Додати менеджерів (Supabase SQL Editor)

INSERT INTO users (telegram_id, name, role)
VALUES
    (535827585, 'Андрій Вовнянко', 'manager'),
    (5009921383, 'Роман Ковальов', 'manager'),
    (7770797356, 'Павло Ковалишин', 'manager')
ON CONFLICT (telegram_id) DO UPDATE
SET name = EXCLUDED.name,
    role = EXCLUDED.role,
    supervisor_id = NULL;
