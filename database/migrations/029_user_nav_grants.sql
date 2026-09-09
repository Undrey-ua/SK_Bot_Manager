-- Додатковий доступ користувача до розділів веб-панелі (через кому).
-- Для менеджера зі збуту базово: analytics,reserves; адмін може додати visits,clients,tasks,stand_warehouse.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS nav_grants VARCHAR(200) NOT NULL DEFAULT '';

COMMENT ON COLUMN users.nav_grants IS 'Додаткові розділи панелі: visits,clients,tasks,stand_warehouse';
