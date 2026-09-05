-- Analysis credits: meters the expensive deep film analysis (~$50/game COGS).
--
-- Two buckets per org: `included` (granted by the plan each month, resets on renewal)
-- and `purchased` (top-up packs, which roll over). A billable analysis spends one
-- credit, taken from `included` first then `purchased`, and it is refunded if the run
-- fails. The free Live Game Logger never touches credits.
--
-- OPT-IN BY ROW: an org WITHOUT an org_credits row is not on the credit system, the
-- legacy monthly-cap path in routers/ai_detect.py still governs it. This lets the
-- system ship without breaking existing orgs or the analysis test suite; new
-- registrations and paid subscriptions create the row and come under credits.

CREATE TABLE IF NOT EXISTS org_credits (
    organization_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    included        integer NOT NULL DEFAULT 0,
    purchased       integer NOT NULL DEFAULT 0,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Append-only audit of every credit movement.
CREATE TABLE IF NOT EXISTS credit_ledger (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind             text NOT NULL,           -- grant | trial_grant | purchase | spend | refund
    amount           integer NOT NULL,        -- signed total: +grant/purchase/refund, -spend
    included_delta   integer NOT NULL DEFAULT 0,
    purchased_delta  integer NOT NULL DEFAULT 0,
    ref              text,                     -- job id (spend/refund) or stripe invoice/session id
    note             text,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_credit_ledger_org ON credit_ledger (organization_id, created_at);
CREATE INDEX IF NOT EXISTS ix_credit_ledger_ref ON credit_ledger (ref);
