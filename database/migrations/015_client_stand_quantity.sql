-- Кількість встановлених стендів на ТТ (як у матриці SK_Account: 2, 3 …)

ALTER TABLE client_stands
    ADD COLUMN IF NOT EXISTS quantity INT NOT NULL DEFAULT 1 CHECK (quantity >= 1);
