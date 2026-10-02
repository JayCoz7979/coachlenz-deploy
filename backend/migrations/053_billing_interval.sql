-- Annual billing support. Record the active subscription's cadence so the monthly
-- included-allotment reset can cover annual subscribers (whose invoice.payment_succeeded,
-- and thus the invoice-driven reset, only fires once a year). Existing rows default to
-- "monthly", which matches their current behavior exactly.
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS billing_interval text NOT NULL DEFAULT 'monthly';
