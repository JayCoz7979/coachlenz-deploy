-- Live Game Play Logger: optional per-report generation parameters.
-- Used by the halftime report to scope the report to first-half events only,
-- without a subset table. NULL for every existing report, so this is a no-op
-- for the entire scout/film report history. Additive and idempotent.
ALTER TABLE tendency_reports ADD COLUMN IF NOT EXISTS params JSONB;
