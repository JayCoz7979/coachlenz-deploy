-- 068: stop the $7 Live Tracker double charge (Stage 2 QA M1).
--
-- Two tabs could each open their own Stripe Checkout and both be paid, because the
-- checkout endpoint only refused (409) AFTER the webhook had granted access.
--   * organizations.live_tracker_open_session_id / _expires_at: the org's one open
--     Checkout Session. The checkout endpoint locks the org row, reuses this session
--     while Stripe still reports it open, and only then creates a new one.
--   * live_tracker_extra_payments: any PAID $7 session for an org that already has the
--     unlock from a different session. Recorded for a human to refund (no auto-refund).
--
-- Numbered 068: 065 is #296, 066 is the $7 grant, 067 is the Halftime PDF leads.
-- Idempotent; only ADDS nullable columns and a new table. Old code ignores both.
-- The reverse lives in backend/migrations/down/ (the runner never applies that folder).

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS live_tracker_open_session_id text,
    ADD COLUMN IF NOT EXISTS live_tracker_open_session_expires_at timestamptz;

CREATE TABLE IF NOT EXISTS live_tracker_extra_payments (
    checkout_session_id text PRIMARY KEY,
    organization_id     uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    payment_intent_id   text,
    amount_total        integer,
    currency            text,
    needs_refund        boolean NOT NULL DEFAULT true,
    refunded_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_live_tracker_extra_payments_refund
    ON live_tracker_extra_payments (needs_refund, created_at DESC);
