-- Report failure transparency: when generation errors (e.g. the Anthropic usage
-- limit), record why so the UI can stop the infinite "Analyzing…" spinner and offer
-- a retry, instead of a report that never sets generated_at. error_reason holds the
-- real reason for the founder/admin/logs; the coach only ever sees a generic message.
ALTER TABLE tendency_reports ADD COLUMN IF NOT EXISTS error_reason text;
