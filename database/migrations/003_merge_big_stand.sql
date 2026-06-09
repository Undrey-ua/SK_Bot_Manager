-- Об'єднати три стенди BIG:* в один «BIG». Виконайте в Supabase SQL Editor.

INSERT INTO stands (name, sort_order, is_active)
VALUES ('BIG', 1, TRUE)
ON CONFLICT (name) DO UPDATE SET is_active = TRUE, sort_order = 1;

-- Прив'язати клієнтів до BIG, якщо були старі варіанти
INSERT INTO client_stands (client_id, stand_id)
SELECT DISTINCT cs.client_id, (SELECT id FROM stands WHERE name = 'BIG')
FROM client_stands cs
JOIN stands s ON s.id = cs.stand_id
WHERE s.name IN ('BIG: Carmelita', 'BIG: Pureloc40', 'BIG: Novocore Legacy')
ON CONFLICT (client_id, stand_id) DO NOTHING;

DELETE FROM client_stands
WHERE stand_id IN (
    SELECT id FROM stands
    WHERE name IN ('BIG: Carmelita', 'BIG: Pureloc40', 'BIG: Novocore Legacy')
);

UPDATE stands
SET is_active = FALSE
WHERE name IN ('BIG: Carmelita', 'BIG: Pureloc40', 'BIG: Novocore Legacy');
