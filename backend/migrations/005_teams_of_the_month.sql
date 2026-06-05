-- Team Submissions for Teams of the Month
CREATE TABLE team_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submitter_name TEXT NOT NULL,
    submitter_email TEXT NOT NULL,
    team_name TEXT NOT NULL,
    sport TEXT NOT NULL,
    school_or_org TEXT NOT NULL,
    level TEXT,
    achievement TEXT NOT NULL,
    season TEXT,
    month_year TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','featured')),
    votes INTEGER NOT NULL DEFAULT 0,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(submitter_email, month_year)
);

-- Featured Teams
CREATE TABLE featured_teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL REFERENCES team_submissions(id),
    month_year TEXT NOT NULL UNIQUE,
    display_order INTEGER NOT NULL DEFAULT 0,
    featured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_submissions_month ON team_submissions(month_year);
CREATE INDEX idx_submissions_status ON team_submissions(status);
CREATE INDEX idx_featured_month ON featured_teams(month_year);
