-- Give every marketing lead an unsubscribe token.
--
-- 057 added marketing_leads.unsubscribe_token with no backfill, so rows from
-- before 057 have none, and an email to them could not carry a working
-- one-click link. New leads already get secrets.token_urlsafe(32), and a
-- repeat signup now fills a missing one (services/waitlist_capture.py).
--
-- Each null or blank token becomes 43 characters of URL-safe base64 without
-- padding, the same shape token_urlsafe(32) makes: 32 bytes from two
-- gen_random_uuid() values (core Postgres, no pgcrypto). Valid tokens are
-- never replaced. Every changed row is recorded in
-- marketing_leads_token_backfill_061 so the down can undo exactly these rows.
--
-- Also adds a unique index on the token (nulls allowed), since the
-- unsubscribe lookup expects at most one row per token.
--
-- This file does not send email. The backend preDeploy command applies it.
-- Reverse by hand with 061_marketing_lead_unsubscribe_token.down.sql.
-- Do not run this by hand against production.

CREATE TABLE IF NOT EXISTS marketing_leads_token_backfill_061 (
    lead_id uuid PRIMARY KEY,
    old_token text,
    new_token text NOT NULL,
    backfilled_at timestamptz NOT NULL DEFAULT now()
);

WITH targets AS (
    SELECT
        id,
        unsubscribe_token AS old_token,
        rtrim(
            translate(
                encode(
                    decode(
                        replace(gen_random_uuid()::text, '-', '')
                        || replace(gen_random_uuid()::text, '-', ''),
                        'hex'
                    ),
                    'base64'
                ),
                '+/', '-_'
            ),
            '='
        ) AS new_token
    FROM marketing_leads
    WHERE unsubscribe_token IS NULL OR btrim(unsubscribe_token) = ''
    FOR UPDATE
),
recorded AS (
    INSERT INTO marketing_leads_token_backfill_061 (lead_id, old_token, new_token)
    SELECT id, old_token, new_token FROM targets
    ON CONFLICT (lead_id) DO NOTHING
    RETURNING lead_id, new_token
)
UPDATE marketing_leads AS m
    SET unsubscribe_token = recorded.new_token
    FROM recorded
    WHERE m.id = recorded.lead_id;

CREATE UNIQUE INDEX IF NOT EXISTS marketing_leads_unsubscribe_token_key
    ON marketing_leads (unsubscribe_token)
    WHERE unsubscribe_token IS NOT NULL;
