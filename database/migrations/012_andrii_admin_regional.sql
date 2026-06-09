-- Андрій Вовнянко: адмін системи + регіональний менеджер (поле Київ тощо)
-- role = admin; у фільтрах/імпорті він у REGIONAL_MANAGER_TELEGRAM_IDS (config/team.py)

INSERT INTO users (telegram_id, name, role)
VALUES (535827585, 'Андрій Вовнянко', 'admin')
ON CONFLICT (telegram_id) DO UPDATE
SET name = EXCLUDED.name,
    role = 'admin',
    supervisor_id = NULL;
