-- 008_add_ai_detect_job_type.sql
-- Allow the new 'ai_detect' job type (AI automated play detection) in the jobs table.

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_job_type_check;

ALTER TABLE jobs ADD CONSTRAINT jobs_job_type_check
    CHECK (job_type IN ('ingest','analysis','report','package','referral_credit','drip_email','survey','ai_detect'));
