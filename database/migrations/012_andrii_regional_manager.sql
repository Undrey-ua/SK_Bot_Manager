-- Андрій Вовнянко — регіональний менеджер (разом із Романом і Павлом)

INSERT INTO users (telegram_id, name, role)
VALUES (535827585, 'Андрій Вовнянко', 'manager')
ON CONFLICT (telegram_id) DO UPDATE
SET name = EXCLUDED.name,
    role = 'manager',
    supervisor_id = NULL;
