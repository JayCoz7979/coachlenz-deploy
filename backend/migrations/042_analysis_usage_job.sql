-- Finding #4 (refund-on-failure): link each analysis_usage row to the job it
-- billed, so the worker can reverse the charge when a run fails/dead-letters
-- (a coach must not be charged for an analysis that never delivered). Nullable +
-- no FK: jobs are pruned on game delete, and an absent link just means "not
-- refundable this way" (harmless). Indexed for the by-job lookup on failure.
ALTER TABLE analysis_usage ADD COLUMN IF NOT EXISTS job_id uuid;
CREATE INDEX IF NOT EXISTS ix_analysis_usage_job_id ON analysis_usage (job_id);
