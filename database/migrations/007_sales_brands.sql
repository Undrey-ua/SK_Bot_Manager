-- Бренди та продажі

CREATE TABLE IF NOT EXISTS brands (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales (
    id BIGSERIAL PRIMARY KEY,
    manager_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    brand_id BIGINT NOT NULL REFERENCES brands(id),
    quantity NUMERIC(12, 2) NOT NULL,
    comment TEXT,
    sold_at DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sales_manager ON sales(manager_id);
CREATE INDEX IF NOT EXISTS idx_sales_client ON sales(client_id);
CREATE INDEX IF NOT EXISTS idx_sales_brand ON sales(brand_id);
CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales(sold_at);

INSERT INTO brands (name, sort_order) VALUES
    ('BIG: Carmelita', 1),
    ('BIG: Novocore Legacy', 2),
    ('BIG: Pureloc40', 3),
    ('ADO', 4),
    ('BerryAlloc: Smartline', 5),
    ('XpertPro', 6),
    ('IVC: Divino', 7),
    ('Prisma', 8),
    ('Tarkett: Express', 9),
    ('Tarkett Living', 10),
    ('Tarkett Herringbone', 11)
ON CONFLICT (name) DO NOTHING;
