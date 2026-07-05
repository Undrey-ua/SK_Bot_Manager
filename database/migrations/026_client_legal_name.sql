-- Юридична назва торгової точки (ТОВ / ФОП)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS legal_name VARCHAR(500);

COMMENT ON COLUMN clients.legal_name IS 'Юридична назва контрагента (ТОВ, ФОП тощо)';
