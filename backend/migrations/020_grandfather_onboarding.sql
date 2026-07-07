-- Grandfather every existing organization as onboarding-complete. Onboarding
-- (verify email + phone, then lock a sport) is a NEW-signup requirement; accounts
-- that predate it must not get trapped in the flow. This runs once: all orgs that
-- exist at migration time are marked complete; signups created afterward start
-- with the default (false) and go through onboarding.
UPDATE organizations SET onboarding_completed = true WHERE onboarding_completed = false;
