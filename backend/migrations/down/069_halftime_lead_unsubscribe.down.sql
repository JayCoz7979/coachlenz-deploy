-- Reverse of 069_halftime_lead_unsubscribe.sql. Never applied by the migration runner.
-- Unsubscribed leads are DELETED first (they asked not to be emailed; they cannot be
-- put back to pending/confirmed without losing that request).
DELETE FROM halftime_pdf_leads WHERE status = 'unsubscribed';
ALTER TABLE halftime_pdf_leads DROP CONSTRAINT IF EXISTS halftime_pdf_leads_status_check;
ALTER TABLE halftime_pdf_leads ADD CONSTRAINT halftime_pdf_leads_status_check
    CHECK (status IN ('pending', 'confirmed'));
ALTER TABLE halftime_pdf_leads DROP COLUMN IF EXISTS unsubscribed_at;
DELETE FROM schema_migrations WHERE filename = '069_halftime_lead_unsubscribe.sql';
