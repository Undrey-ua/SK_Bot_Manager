-- Схожі назви міст і порожній дубль області «Івано Франківська».

UPDATE clients
SET city = 'Івано-Франківськ'
WHERE city IS NOT NULL
  AND regexp_replace(lower(btrim(city)), '[[:space:]–—-]+', ' ', 'g') = 'івано франківськ'
  AND city IS DISTINCT FROM 'Івано-Франківськ';

UPDATE clients
SET city = 'Камінь-Каширський'
WHERE city IS NOT NULL
  AND regexp_replace(lower(btrim(city)), '[[:space:]–—-]+', ' ', 'g') = 'камінь каширський'
  AND city IS DISTINCT FROM 'Камінь-Каширський';

UPDATE clients
SET city = 'Вознесенськ'
WHERE city IS NOT NULL
  AND regexp_replace(
        lower(btrim(regexp_replace(city, '^(м|с)\.[[:space:]]*', '', 'i'))),
        '[[:space:]–—-]+',
        ' ',
        'g'
      ) IN ('вознесеньск', 'вознесенськ')
  AND city IS DISTINCT FROM 'Вознесенськ';

UPDATE clients
SET city = 'Мукачево'
WHERE city IS NOT NULL
  AND lower(btrim(city)) IN ('укачево', 'мукачево')
  AND city IS DISTINCT FROM 'Мукачево';

UPDATE clients
SET city = btrim(regexp_replace(city, '^(м|с)\.[[:space:]]*', '', 'i'))
WHERE city ~* '^(м|с)\.';

DELETE FROM manager_regions AS duplicate
WHERE NOT EXISTS (SELECT 1 FROM clients WHERE region_id = duplicate.id)
  AND NOT EXISTS (SELECT 1 FROM reserves WHERE region_id = duplicate.id)
  AND EXISTS (
      SELECT 1
      FROM manager_regions AS canonical
      WHERE canonical.manager_id = duplicate.manager_id
        AND canonical.id <> duplicate.id
        AND regexp_replace(lower(canonical.name), '[[:space:]–—-]+', '', 'g')
            = regexp_replace(lower(duplicate.name), '[[:space:]–—-]+', '', 'g')
        AND (
            canonical.name LIKE '%-%'
            OR (duplicate.name NOT LIKE '%-%' AND canonical.id < duplicate.id)
        )
  );
