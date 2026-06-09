-- Місто окремо від коментаря
ALTER TABLE clients ADD COLUMN IF NOT EXISTS city VARCHAR(200);

UPDATE clients
SET
    city = trim(substring(comment FROM position(':' IN comment) + 1)),
    comment = NULL
WHERE comment ~* '^[[:space:]]*місто[[:space:]]*:'
  AND (city IS NULL OR trim(city) = '');
