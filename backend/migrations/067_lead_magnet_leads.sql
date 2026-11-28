-- 067: leads for the free printable Halftime Sheet PDF on /live-tracker.
-- A visitor trades name + a valid email (phone OPTIONAL) for a download link to the
-- printable tracker. Dedicated table (not marketing_leads) so the consent text, the
-- optional phone, and the download token live with the lead. The phone is stored only
-- because the visitor volunteered it; nothing in CoachLenz texts it (no SMS).
-- Numbered 067: 056-061 are claimed by open PRs (#292/#293/#294), 065 is #296,
-- 066 is the Live Tracker entitlement. Only CREATEs; old code ignores it. Idempotent.
-- The reverse lives in backend/migrations/down/ (the runner never applies that folder).

CREATE TABLE IF NOT EXISTS lead_magnet_leads (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source           text NOT NULL DEFAULT 'halftime_pdf',
    name             text NOT NULL,
    email            text NOT NULL,
    phone            text,
    consent_email    boolean NOT NULL DEFAULT false,
    consent_text     text,
    download_token   text NOT NULL,
    ip_address       text,
    user_agent       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- One row per (email, source): a repeat submission refreshes the row instead of
-- piling up duplicates.
CREATE UNIQUE INDEX IF NOT EXISTS ux_lead_magnet_email_source
    ON lead_magnet_leads (lower(email), source);
CREATE UNIQUE INDEX IF NOT EXISTS ux_lead_magnet_download_token
    ON lead_magnet_leads (download_token);
CREATE INDEX IF NOT EXISTS ix_lead_magnet_source_created
    ON lead_magnet_leads (source, created_at DESC);
