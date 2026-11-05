-- Поділ торгових марок BIG і Tarkett.
-- Стенди BIG і Tarkett SPC не чіпаємо. Історичні продажі лишаються на старих brand_id.
-- Той самий крок виконує старт бота і веб-панелі (database/brand_sync.py). Повтор безпечний.

INSERT INTO brands (name, sort_order, is_active) VALUES
    ('BIG: Novocore LVT', 3, TRUE),
    ('BIG: Novocore LVT HB', 4, TRUE),
    ('BIG: Novocore SPC', 5, TRUE),
    ('BIG: Novocore SPC HB', 6, TRUE),
    ('Tarkett: SPC Living 55', 7, TRUE),
    ('Tarkett: SPC Herringbone 55', 8, TRUE)
ON CONFLICT (name) DO UPDATE
SET is_active = TRUE,
    sort_order = EXCLUDED.sort_order;

UPDATE brands SET sort_order = 1, is_active = TRUE WHERE name = 'BIG: Carmelita';
UPDATE brands SET sort_order = 2, is_active = TRUE WHERE name = 'BIG: Pureloc40';

UPDATE brands
SET sort_order = sort_order + 20
WHERE is_active IS TRUE
  AND sort_order > 0
  AND sort_order <= 11
  AND name NOT IN (
    'BIG: Carmelita',
    'BIG: Pureloc40',
    'BIG: Novocore LVT',
    'BIG: Novocore LVT HB',
    'BIG: Novocore SPC',
    'BIG: Novocore SPC HB',
    'Tarkett: SPC Living 55',
    'Tarkett: SPC Herringbone 55'
  );

INSERT INTO client_swatches (client_id, brand_id)
SELECT DISTINCT cs.client_id, nb.id
FROM client_swatches cs
JOIN brands ob ON ob.id = cs.brand_id
JOIN brands nb ON nb.name IN (
    'BIG: Novocore LVT',
    'BIG: Novocore LVT HB',
    'BIG: Novocore SPC',
    'BIG: Novocore SPC HB'
)
WHERE ob.name IN ('BIG: Novocore Legacy', 'BIG: Novocore', 'Novocore Legacy', 'Novocore')
ON CONFLICT (client_id, brand_id) DO NOTHING;

INSERT INTO client_swatches (client_id, brand_id)
SELECT DISTINCT cs.client_id, nb.id
FROM client_swatches cs
JOIN brands ob ON ob.id = cs.brand_id
JOIN brands nb ON nb.name IN (
    'Tarkett: SPC Living 55',
    'Tarkett: SPC Herringbone 55'
)
WHERE ob.name IN ('Tarkett SPC', 'Tarkett')
ON CONFLICT (client_id, brand_id) DO NOTHING;

DELETE FROM client_swatches
WHERE brand_id IN (
    SELECT id FROM brands
    WHERE name IN (
        'BIG: Novocore Legacy',
        'BIG: Novocore',
        'Novocore Legacy',
        'Novocore',
        'Tarkett SPC',
        'Tarkett'
    )
);

UPDATE brands
SET is_active = FALSE,
    sort_order = 200
WHERE name IN (
    'BIG: Novocore Legacy',
    'BIG: Novocore',
    'Novocore Legacy',
    'Novocore',
    'Tarkett SPC',
    'Tarkett'
);
