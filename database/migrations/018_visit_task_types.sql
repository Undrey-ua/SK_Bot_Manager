CREATE TABLE IF NOT EXISTS visit_task_types (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    label VARCHAR(200) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO visit_task_types (code, label, sort_order) VALUES
    ('stand_control', 'Контроль стенду', 10),
    ('photo', 'Фото', 20),
    ('order', 'Замовлення', 30),
    ('price_control', 'Контроль цін', 40),
    ('seller_training', 'Навчання продавця', 50),
    ('new_products', 'Презентація новинок', 60),
    ('inkassation', 'Інкасація', 70)
ON CONFLICT (code) DO NOTHING;
