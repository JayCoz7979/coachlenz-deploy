-- 069: one-click unsubscribe for the free Halftime Sheet PDF leads (Stage 2 QA M2).
-- Adds status 'unsubscribed' and unsubscribed_at. The unsubscribe link and the
-- List-Unsubscribe header carry an HMAC-signed token for the lead id, so nothing new
-- is stored for it. An unsubscribed lead gets no further lead email unless the coach
-- submits the form again (a new, explicit double opt-in).
-- Idempotent. The reverse lives in backend/migrations/down/.

ALTER TABLE halftime_pdf_leads
    ADD COLUMN IF NOT EXISTS unsubscribed_at timestamptz;

ALTER TABLE halftime_pdf_leads DROP CONSTRAINT IF EXISTS halftime_pdf_leads_status_check;
ALTER TABLE halftime_pdf_leads ADD CONSTRAINT halftime_pdf_leads_status_check
    CHECK (status IN ('pending', 'confirmed', 'unsubscribed'));
