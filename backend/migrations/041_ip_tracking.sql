-- Chargeback defense: capture the client IP at signup and at every checkout so a
-- disputed charge can be tied to an originating IP + timestamp. This replaces the
-- (removed) SMS/phone verification as the anti-fraud / dispute-evidence signal.
-- uvicorn runs with --proxy-headers --forwarded-allow-ips=* so request.client.host
-- is the real end-user IP behind Railway's proxy.
ALTER TABLE users ADD COLUMN IF NOT EXISTS signup_ip TEXT;

-- One row per checkout attempt. id is always supplied by the ORM (uuid4), so no DB
-- default is needed (keeps this migration independent of pgcrypto/gen_random_uuid).
CREATE TABLE IF NOT EXISTS purchase_ip_log (
    id                UUID PRIMARY KEY,
    organization_id   UUID NOT NULL,
    user_id           UUID,
    ip                TEXT,
    user_agent        TEXT,
    tier              TEXT,
    stripe_session_id TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_purchase_ip_log_org ON purchase_ip_log(organization_id);
CREATE INDEX IF NOT EXISTS ix_purchase_ip_log_session ON purchase_ip_log(stripe_session_id);
