-- 009_source_connections.sql
-- Stores a coach/org's encrypted login for external film sources (Hudl, NFHS)
-- so the ingest worker can authenticate a headless capture for private/paid film.

CREATE TABLE IF NOT EXISTS source_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    account_email TEXT,
    encrypted_credentials BYTEA NOT NULL,
    status TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected','error')),
    last_error TEXT,
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_org_provider UNIQUE (organization_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_source_connections_org ON source_connections(organization_id);
