-- Stripe webhook idempotency. Stripe delivers events at-least-once and WILL
-- redeliver; the event id as PK makes a redelivery collide on insert so the handler
-- skips it, preventing double-applied effects (e.g. duplicate referral credits).
CREATE TABLE IF NOT EXISTS processed_stripe_events (
    event_id     TEXT PRIMARY KEY,
    event_type   TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
