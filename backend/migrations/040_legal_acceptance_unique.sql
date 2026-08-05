-- Finding #24: the consent ledger accreted duplicate rows because record_acceptance
-- inserted unconditionally and the accept flow's read-check races. Dedupe the
-- historical rows (keep the earliest per group), then enforce one authoritative
-- acceptance per (org, user, document, version). Idempotent / re-runnable.

DELETE FROM legal_acceptances a
USING legal_acceptances b
WHERE a.id > b.id
  AND a.organization_id = b.organization_id
  AND a.user_id IS NOT DISTINCT FROM b.user_id
  AND a.document = b.document
  AND a.version = b.version;

CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_acceptance
  ON legal_acceptances (organization_id, user_id, document, version);
