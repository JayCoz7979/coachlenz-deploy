-- Per-account learning loop (Engine §14).
--
-- "One account. One model. One truth." Every table is org-scoped and CASCADE-
-- deletes with the organization, so one coach's corrections never touch another
-- account's analyses and everything is gone within the account-deletion cascade.
--
-- Flow: a coach edits a play the AI tagged -> we record the (old -> new) label
-- correction (coach_label_corrections) and roll a per-account quality score
-- (label_quality_scores). When the SAME AI mislabel is corrected the same way
-- enough times, we propose an account adjustment (account_learning_adjustments)
-- the coach can accept/reject; an active adjustment relabels matching plays in
-- that account's future reports. No credits are consumed by any of this.

-- Manual Mode: a coach can opt out of the auto-loop (still records corrections,
-- but stops proposing/applying adjustments). Settings > Learning Loop.
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS learning_loop_manual boolean NOT NULL DEFAULT false;


-- Raw signal: one row per label field a coach changed on a play.
CREATE TABLE IF NOT EXISTS coach_label_corrections (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id   uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id           uuid REFERENCES users(id) ON DELETE SET NULL,
    event_id          uuid REFERENCES events(id) ON DELETE CASCADE,
    game_id           uuid,
    sport             text NOT NULL,
    field             text NOT NULL,              -- e.g. 'coverage', 'play_type', 'shot_zone'
    category          text,                        -- play_type bucket the correction sits in
    old_value         text,                        -- what the AI (or a prior tag) had
    new_value         text,                        -- what the coach set
    was_auto_detected boolean NOT NULL DEFAULT false,  -- true = correcting the AI
    ai_confidence     double precision,            -- the AI's confidence on that play
    signal            text NOT NULL,               -- 'high' | 'low' | 'reclass'
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_corrections_org_field
    ON coach_label_corrections (organization_id, sport, field);
CREATE INDEX IF NOT EXISTS ix_corrections_org_created
    ON coach_label_corrections (organization_id, created_at);


-- Proposed / active per-account relabels distilled from systematic corrections.
CREATE TABLE IF NOT EXISTS account_learning_adjustments (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    sport            text NOT NULL,
    field            text NOT NULL,
    from_value       text NOT NULL,               -- AI label to normalize away from
    to_value         text NOT NULL,               -- coach's preferred label
    support_count    integer NOT NULL DEFAULT 0,  -- how many corrections back this
    status           text NOT NULL DEFAULT 'pending',  -- pending | active | rejected
    note             text,
    activated_by     uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- One live proposal per (org, sport, field, from->to). Upserted as support grows.
CREATE UNIQUE INDEX IF NOT EXISTS ux_adjustment_mapping
    ON account_learning_adjustments (organization_id, sport, field, from_value, to_value);
CREATE INDEX IF NOT EXISTS ix_adjustment_org_status
    ON account_learning_adjustments (organization_id, status);


-- Rolling per-account label-quality counters (one row per org).
CREATE TABLE IF NOT EXISTS label_quality_scores (
    organization_id   uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    total_corrections integer NOT NULL DEFAULT 0,
    high_count        integer NOT NULL DEFAULT 0,   -- added specificity to the AI
    low_count         integer NOT NULL DEFAULT 0,   -- removed detail (likely misclick)
    reclass_count     integer NOT NULL DEFAULT 0,   -- relabeled A -> B
    systematic_count  integer NOT NULL DEFAULT 0,   -- corrections that became adjustments
    updated_at        timestamptz NOT NULL DEFAULT now()
);
