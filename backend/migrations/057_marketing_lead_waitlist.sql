-- Waitlist columns on marketing_leads.
--
-- Additive and nullable, except has_account which defaults to false so older
-- rows are "no account yet". The lower(email) unique index from migration 045
-- is unchanged. This file does not send email.
--
-- Numbered 057 because 056_games_r2_key_unique.sql belongs to the upload fix.
-- The runner applies forward files in name order and ignores *.down.sql.
--
-- Do not run this by hand against production. The backend preDeploy command
-- applies it. Reverse by hand with 057_marketing_lead_waitlist.down.sql.

ALTER TABLE marketing_leads
    ADD COLUMN IF NOT EXISTS first_name text,
    ADD COLUMN IF NOT EXISTS school text,
    ADD COLUMN IF NOT EXISTS sport text,
    ADD COLUMN IF NOT EXISTS role text,
    ADD COLUMN IF NOT EXISTS role_branch text,
    ADD COLUMN IF NOT EXISTS consent_text_version text,
    ADD COLUMN IF NOT EXISTS lead_magnet text,
    ADD COLUMN IF NOT EXISTS utm_source text,
    ADD COLUMN IF NOT EXISTS utm_medium text,
    ADD COLUMN IF NOT EXISTS utm_campaign text,
    ADD COLUMN IF NOT EXISTS utm_content text,
    ADD COLUMN IF NOT EXISTS utm_term text,
    ADD COLUMN IF NOT EXISTS referrer text,
    ADD COLUMN IF NOT EXISTS landing_path text,
    ADD COLUMN IF NOT EXISTS ref_code text,
    ADD COLUMN IF NOT EXISTS confirm_token_hash text,
    ADD COLUMN IF NOT EXISTS confirm_sent_at timestamptz,
    ADD COLUMN IF NOT EXISTS confirmed_at timestamptz,
    ADD COLUMN IF NOT EXISTS unsubscribed_at timestamptz,
    ADD COLUMN IF NOT EXISTS unsubscribe_token text,
    ADD COLUMN IF NOT EXISTS resend_contact_id text,
    ADD COLUMN IF NOT EXISTS has_account boolean NOT NULL DEFAULT false;
