-- Назви з 1С/каталогу (артикул, упаковки, м²) не вміщаються у VARCHAR(200).

ALTER TABLE reserves
    ALTER COLUMN material TYPE TEXT;

COMMENT ON COLUMN reserves.material IS 'Назва матеріалу (довільний текст з каталогу)';
