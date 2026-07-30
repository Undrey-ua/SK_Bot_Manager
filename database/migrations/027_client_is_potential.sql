ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_potential BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_clients_is_potential ON clients (is_potential) WHERE is_potential = TRUE;
