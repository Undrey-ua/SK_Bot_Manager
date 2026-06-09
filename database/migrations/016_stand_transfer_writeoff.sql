-- Списання стендів: операція write_off без отримувача (to_client_id NULL)

ALTER TABLE stand_transfers
    ADD COLUMN IF NOT EXISTS operation VARCHAR(20) NOT NULL DEFAULT 'move';

ALTER TABLE stand_transfers
    ALTER COLUMN to_client_id DROP NOT NULL;

COMMENT ON COLUMN stand_transfers.operation IS 'move — переміщення, write_off — списання з ТТ';
