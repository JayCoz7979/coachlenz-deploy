-- Channel attribution. Tag every visitor and every signup with the source it came
-- from, so a channel can be judged by qualified traffic (visitors who convert and
-- retain), not raw sessions. Extends the funnel from migration 045; no new table.
--
-- source is a coarse channel label captured on the first visit: a utm_source when
-- present, else the referrer host, else 'direct'. No PII.

ALTER TABLE funnel_events
    ADD COLUMN IF NOT EXISTS source text;

-- The source the account came from, captured once at registration and reused for the
-- server-emitted signup_complete event. Also lets retention later break down by source
-- (the org already carries it), which is the "qualified traffic" link.
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS signup_source text;

CREATE INDEX IF NOT EXISTS ix_funnel_source ON funnel_events (source, event);
