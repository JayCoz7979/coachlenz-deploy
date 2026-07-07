-- Sport entitlement lock. During onboarding a client picks the sport(s) their
-- tier allows; the choice is stored here and enforced on every film-analysis
-- entry point (see backend/services/sports.py). onboarding_completed gates the
-- post-signup flow (verify email + phone, then pick sport).
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS chosen_sports jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS onboarding_completed boolean NOT NULL DEFAULT false;
