-- COPPA/FERPA parent data-access + deletion request flow. Public intake (no login),
-- admin-verified, admin-fulfilled; the row is the audit trail. Deletion fulfillment
-- removes the identified roster records and scrubs the student's jersey from that
-- team's film analysis, then a Deletion Certificate is emailed.
CREATE TABLE IF NOT EXISTS privacy_requests (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_type     text NOT NULL,                 -- 'access' | 'deletion'
    requester_name   text NOT NULL,
    requester_email  text NOT NULL,
    relationship     text NOT NULL,                 -- parent | guardian | eligible_student | school_official | other
    school_or_org    text,
    student_name     text NOT NULL,
    student_details  text,
    details          text,
    status           text NOT NULL DEFAULT 'pending',   -- pending | verified | completed | rejected
    resolution_note  text,
    certificate_id   text,
    organization_id  uuid REFERENCES organizations(id) ON DELETE SET NULL,
    status_token     text NOT NULL,
    ip_address       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    verified_at      timestamptz,
    completed_at     timestamptz
);
CREATE INDEX IF NOT EXISTS ix_privacy_requests_status ON privacy_requests (status, created_at DESC);
