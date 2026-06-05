-- Organizations
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    subscription_tier TEXT NOT NULL DEFAULT 'trial' CHECK (subscription_tier IN ('trial','coach','athletic_dept','district')),
    is_trial BOOLEAN NOT NULL DEFAULT TRUE,
    trial_ends_at TIMESTAMPTZ,
    trial_games_used INTEGER NOT NULL DEFAULT 0,
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT UNIQUE,
    stripe_subscription_status TEXT,
    has_coach_tenure_access BOOLEAN NOT NULL DEFAULT FALSE,
    admin_level TEXT CHECK (admin_level IN ('super','support',NULL)),
    referral_code TEXT UNIQUE,
    referred_by_org_id UUID REFERENCES organizations(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner','admin','coach','member')),
    phone TEXT,
    phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    avatar_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Teams
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sport TEXT NOT NULL CHECK (sport IN ('football','flag_football','basketball','baseball','softball','volleyball','soccer')),
    level TEXT,
    season TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Games
CREATE TABLE games (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id),
    title TEXT NOT NULL,
    sport TEXT NOT NULL,
    opponent TEXT,
    game_date DATE,
    is_home BOOLEAN,
    r2_key TEXT,
    r2_url TEXT,
    r2_expires_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    file_size_bytes BIGINT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','ready','error')),
    error_message TEXT,
    is_trial_game BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Clips
CREATE TABLE clips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title TEXT,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    r2_key TEXT,
    r2_url TEXT,
    r2_expires_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Events
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    clip_id UUID REFERENCES clips(id),
    event_type TEXT NOT NULL,
    time_seconds FLOAT,
    down INTEGER,
    distance INTEGER,
    field_position TEXT,
    hash_position TEXT,
    formation TEXT,
    play_type TEXT,
    result TEXT,
    yards_gained INTEGER,
    personnel TEXT,
    motion BOOLEAN DEFAULT FALSE,
    extra_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tags
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#6366f1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(organization_id, name)
);

CREATE TABLE event_tags (
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, tag_id)
);

CREATE TABLE clip_tags (
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (clip_id, tag_id)
);

-- Tendency Reports
CREATE TABLE tendency_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id),
    game_ids UUID[] NOT NULL DEFAULT '{}',
    sport TEXT NOT NULL,
    report_type TEXT NOT NULL DEFAULT 'opponent' CHECK (report_type IN ('opponent','self_scout','custom')),
    title TEXT NOT NULL,
    summary_json BYTEA,
    prose_sections JSONB DEFAULT '[]',
    is_trial BOOLEAN NOT NULL DEFAULT FALSE,
    watermarked BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Jobs
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (job_type IN ('ingest','analysis','report','package','referral_credit','drip_email','survey')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','error')),
    payload JSONB NOT NULL DEFAULT '{}',
    result JSONB DEFAULT '{}',
    error_message TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_users_org ON users(organization_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_teams_org ON teams(organization_id);
CREATE INDEX idx_games_org ON games(organization_id);
CREATE INDEX idx_games_team ON games(team_id);
CREATE INDEX idx_games_status ON games(status);
CREATE INDEX idx_clips_game ON clips(game_id);
CREATE INDEX idx_clips_org ON clips(organization_id);
CREATE INDEX idx_events_game ON events(game_id);
CREATE INDEX idx_events_org ON events(organization_id);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_reports_org ON tendency_reports(organization_id);
CREATE INDEX idx_jobs_status_type ON jobs(status, job_type);
CREATE INDEX idx_jobs_locked ON jobs(locked_at) WHERE locked_at IS NOT NULL;
