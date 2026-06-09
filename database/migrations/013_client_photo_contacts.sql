-- Загальне фото ТТ та контакти (редагування лише з веб-панелі)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS photo_url VARCHAR(1000);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contacts TEXT;
