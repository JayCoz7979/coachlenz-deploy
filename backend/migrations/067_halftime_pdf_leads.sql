-- 067: free printable Halftime Sheet PDF lead form on /live-tracker (DOUBLE OPT-IN).
--
-- A coach submits name + email (+ optional phone, never texted). The row starts
-- status='pending' and a confirmation email carries a single-use, 24-hour token
-- link. Only the token's HMAC-SHA256 hash is stored (token_hash), never the raw
-- token. Confirming flips the row to 'confirmed' with confirmed_at + confirmed_ip,
-- and only then is the PDF emailed. A used token keeps its hash with token_used_at
-- set so a reused link can be told apart from an unknown one (and offered a resend).
--
-- New table only; old code ignores it. Idempotent.
-- Numbered 067: 056-064 are claimed by open PRs, 065 is #296, 066 is the $7 grant.
-- The reverse lives in backend/migrations/down/ (the runner never applies that folder).

CREATE TABLE IF NOT EXISTS halftime_pdf_leads (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    text NOT NULL,
    email                   text NOT NULL,
    phone                   text,                 -- optional; NEVER texted, no SMS anywhere
    source                  text NOT NULL DEFAULT 'halftime_pdf',
    status                  text NOT NULL DEFAULT 'pending',
    consent_text            text NOT NULL,
    consented_at            timestamptz NOT NULL DEFAULT now(),
    submit_ip               text,
    token_hash              text,                 -- HMAC-SHA256(SECRET_KEY, token), hex
    token_expires_at        timestamptz,
    token_used_at           timestamptz,
    confirmation_sent_at    timestamptz,          -- doubles as the per-address resend cooldown
    confirmation_send_count integer NOT NULL DEFAULT 0,
    confirmed_at            timestamptz,
    confirmed_ip            text,
    pdf_sent_at             timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT halftime_pdf_leads_status_check CHECK (status IN ('pending', 'confirmed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_halftime_pdf_leads_email ON halftime_pdf_leads (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS ux_halftime_pdf_leads_token_hash ON halftime_pdf_leads (token_hash)
    WHERE token_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_halftime_pdf_leads_status ON halftime_pdf_leads (status, created_at DESC);
