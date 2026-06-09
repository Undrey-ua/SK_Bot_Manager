-- Області Андрія Вовнянка (telegram_id 535827585) — лише ці чотири + Київ

-- Видалити помилково додані області (клієнтів спочатку перенесіть до Романа, див. scripts/fix_andrii_regions.py)
DELETE FROM manager_regions mr
USING users u
WHERE mr.manager_id = u.id
  AND u.telegram_id = 535827585
  AND mr.name IN (
    'Дніпропетровська',
    'Харківська',
    'Запорізька',
    'Кіровоградська',
    'Одеська'
  );
