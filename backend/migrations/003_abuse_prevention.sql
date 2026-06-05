-- Device Fingerprints
CREATE TABLE device_fingerprints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint TEXT NOT NULL,
    user_id UUID REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),
    ip_address TEXT,
    user_agent TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_count INTEGER NOT NULL DEFAULT 1,
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE
);

-- Risk Flags
CREATE TABLE risk_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    user_id UUID REFERENCES users(id),
    flag_type TEXT NOT NULL CHECK (flag_type IN ('disposable_email','suspicious_signup','rate_limit_exceeded','multiple_trials','payment_fraud','ip_block')),
    severity TEXT NOT NULL DEFAULT 'low' CHECK (severity IN ('low','medium','high','critical')),
    details JSONB DEFAULT '{}',
    resolved_at TIMESTAMPTZ,
    resolved_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit Logs
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id UUID,
    ip_address TEXT,
    user_agent TEXT,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fingerprints_fp ON device_fingerprints(fingerprint);
CREATE INDEX idx_fingerprints_ip ON device_fingerprints(ip_address);
CREATE INDEX idx_risk_flags_org ON risk_flags(organization_id);
CREATE INDEX idx_audit_logs_org ON audit_logs(organization_id);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at DESC);
