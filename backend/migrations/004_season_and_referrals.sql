-- Referral Codes
CREATE TABLE referral_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    code TEXT UNIQUE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Referrals
CREATE TABLE referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_org_id UUID NOT NULL REFERENCES organizations(id),
    referred_org_id UUID NOT NULL REFERENCES organizations(id),
    referral_code_id UUID REFERENCES referral_codes(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','converted','paid','void')),
    commission_tier INTEGER NOT NULL DEFAULT 1,
    commission_pct NUMERIC(5,2) NOT NULL DEFAULT 10.00,
    stripe_credit_cents INTEGER,
    credited_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Referral Settings (singleton row)
CREATE TABLE referral_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    tier1_pct NUMERIC(5,2) NOT NULL DEFAULT 10.00,
    tier2_pct NUMERIC(5,2) NOT NULL DEFAULT 15.00,
    tier3_pct NUMERIC(5,2) NOT NULL DEFAULT 20.00,
    tier1_min_referrals INTEGER NOT NULL DEFAULT 0,
    tier2_min_referrals INTEGER NOT NULL DEFAULT 3,
    tier3_min_referrals INTEGER NOT NULL DEFAULT 10,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO referral_settings DEFAULT VALUES;

CREATE INDEX idx_referrals_referrer ON referrals(referrer_org_id);
CREATE INDEX idx_referrals_referred ON referrals(referred_org_id);
CREATE INDEX idx_referral_codes_code ON referral_codes(code);
