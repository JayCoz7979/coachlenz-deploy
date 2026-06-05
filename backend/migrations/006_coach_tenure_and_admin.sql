-- Coach Profiles
CREATE TABLE coach_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    name TEXT NOT NULL,
    sport TEXT,
    position TEXT,
    bio TEXT,
    photo_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Coach Moves (tenure tracking)
CREATE TABLE coach_moves (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coach_id UUID NOT NULL REFERENCES coach_profiles(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    school_name TEXT NOT NULL,
    role TEXT,
    sport TEXT,
    start_date DATE,
    end_date DATE,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    wins INTEGER,
    losses INTEGER,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Admin Permissions (for support staff)
CREATE TABLE admin_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    granted_by UUID REFERENCES users(id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, permission)
);

-- Admin Audit Logs
CREATE TABLE admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    target_type TEXT,
    target_id UUID,
    details JSONB DEFAULT '{}',
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Customer Intelligence Survey Prompts
CREATE TABLE survey_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    response_type TEXT NOT NULL DEFAULT 'text' CHECK (response_type IN ('text','rating','multiple_choice')),
    options JSONB DEFAULT '[]',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Survey Responses
CREATE TABLE survey_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    prompt_id UUID NOT NULL REFERENCES survey_prompts(id),
    response_text TEXT,
    response_rating INTEGER,
    response_choice TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default survey prompts
INSERT INTO survey_prompts (question, response_type, display_order) VALUES
('How are you primarily using CoachLenz?', 'multiple_choice', 1),
('What sport does your program focus on most?', 'multiple_choice', 2),
('How satisfied are you with the tendency reports?', 'rating', 3),
('What feature would make the biggest difference for your program?', 'text', 4);

UPDATE survey_prompts SET options = '["Opponent scouting","Self-scout","Recruiting","Staff collaboration","All of the above"]'::jsonb WHERE display_order = 1;
UPDATE survey_prompts SET options = '["Football","Basketball","Baseball","Softball","Volleyball","Soccer","Flag Football"]'::jsonb WHERE display_order = 2;

CREATE INDEX idx_coach_profiles_org ON coach_profiles(organization_id);
CREATE INDEX idx_coach_moves_coach ON coach_moves(coach_id);
CREATE INDEX idx_survey_responses_org ON survey_responses(organization_id);
CREATE INDEX idx_admin_audit_logs_admin ON admin_audit_logs(admin_user_id);
