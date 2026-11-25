-- Store the browser User-Agent on a legal acceptance. Nullable so every row
-- written before this migration stays null. Nothing else reads the column.
-- The migrator ignores the matching .down.sql file.
-- Do not run this by hand against production.

ALTER TABLE legal_acceptances
    ADD COLUMN IF NOT EXISTS user_agent text;
