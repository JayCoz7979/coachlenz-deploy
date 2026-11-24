-- Waitlist fields on the existing marketing_leads table.
--
-- POST /leads already stores a volunteered email. The coming-soon form also asks
-- for an optional school and sport. Both columns are nullable so older rows, and
-- callers that only send an email, keep working. The lower(email) unique index
-- from migration 045 is unchanged: a repeat address updates these fields instead
-- of inserting a second row.
--
-- Applied by the existing backend preDeploy runner (python -m backend.migrate).
-- Do not run this file by hand against production.

ALTER TABLE marketing_leads
    ADD COLUMN IF NOT EXISTS school text,
    ADD COLUMN IF NOT EXISTS sport text;
