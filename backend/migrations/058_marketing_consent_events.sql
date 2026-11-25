-- Append-only consent log and a suppression list for the waitlist.
--
-- marketing_consent_events is insert-only. The application does not update or
-- delete these rows. email_suppressions survives lead deletion: it stores a
-- sha256 of the lowercased email, not the address.
--
-- reminder_sent_at marks the single 48 hour confirm reminder.
-- The migrator ignores the matching .down.sql file.
-- Do not run this by hand against production.

ALTER TABLE marketing_leads
    ADD COLUMN IF NOT EXISTS reminder_sent_at timestamptz,
    ADD COLUMN IF NOT EXISTS a1_sent_at timestamptz,
    ADD COLUMN IF NOT EXISTS l1m_sent_at timestamptz,
    ADD COLUMN IF NOT EXISTS minor_reclass_at timestamptz;

CREATE TABLE IF NOT EXISTS marketing_consent_events (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id               uuid REFERENCES marketing_leads(id) ON DELETE SET NULL,
    event_type            text NOT NULL,
    occurred_at           timestamptz NOT NULL DEFAULT now(),
    email                 text NOT NULL,
    consent_text          text,
    consent_version       text,
    consent_text_sha256   text,
    page_url              text,
    form_id               text,
    utm_source            text,
    utm_medium            text,
    utm_campaign          text,
    utm_content           text,
    utm_term              text,
    referrer              text,
    role                  text,
    ip_address            text,
    user_agent            text,
    doi_sent_at           timestamptz,
    doi_confirmed_at      timestamptz,
    unsubscribe_method    text,
    resend_message_id     text,
    CONSTRAINT marketing_consent_events_type_check CHECK (
        event_type IN (
            'signup', 'doi_confirmed', 'unsubscribed', 'resubscribed',
            'deleted', 'complaint', 'bounce'
        )
    )
);

CREATE TABLE IF NOT EXISTS email_suppressions (
    email_sha256   text PRIMARY KEY,
    suppressed_at  timestamptz NOT NULL DEFAULT now(),
    reason         text NOT NULL
);
