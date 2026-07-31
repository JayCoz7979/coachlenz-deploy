-- Legal + COPPA/FERPA consent logging (beta-readiness P0 #2).
--
-- Records each acceptance of Terms / Privacy (per user, at signup) and the
-- student-data authority attestation (per org, before any student roster data is
-- entered). Versioned so a re-acceptance is required when the legal text is
-- finalized/changed by the attorney.

CREATE TABLE IF NOT EXISTS legal_acceptances (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         uuid REFERENCES users(id) ON DELETE SET NULL,
    document        text NOT NULL,            -- 'terms' | 'privacy' | 'student_data'
    version         text NOT NULL,
    ip_address      text,
    accepted_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_legal_acceptances_org_doc
    ON legal_acceptances (organization_id, document);
