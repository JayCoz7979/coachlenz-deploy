-- CoachLenz Initial Schema
-- Project: mbkstodswexxvdgyunio
-- Schema: coachlenz

CREATE SCHEMA IF NOT EXISTS coachlenz;

-- ============================================================
-- TABLE: teams
-- ============================================================
CREATE TABLE IF NOT EXISTS coachlenz.teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    sport TEXT NOT NULL CHECK (sport IN ('football','basketball','baseball','softball','soccer','volleyball')),
    season TEXT,
    head_coach TEXT,
    school TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE coachlenz.teams ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass_teams" ON coachlenz.teams
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================
-- TABLE: players
-- ============================================================
CREATE TABLE IF NOT EXISTS coachlenz.players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES coachlenz.teams(id) ON DELETE CASCADE,
    name TEXT,
    jersey_number TEXT,
    position TEXT,
    grade_year TEXT,
    email TEXT,
    phone TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active','injured','inactive')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE coachlenz.players ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass_players" ON coachlenz.players
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================
-- TABLE: games
-- ============================================================
CREATE TABLE IF NOT EXISTS coachlenz.games (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES coachlenz.teams(id) ON DELETE CASCADE,
    opponent TEXT NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    location TEXT,
    home_away TEXT DEFAULT 'home' CHECK (home_away IN ('home','away','neutral')),
    our_score INTEGER,
    opponent_score INTEGER,
    result TEXT CHECK (result IN ('win','loss','tie', NULL)),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE coachlenz.games ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass_games" ON coachlenz.games
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================
-- TABLE: player_stats
-- ============================================================
CREATE TABLE IF NOT EXISTS coachlenz.player_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID REFERENCES coachlenz.players(id) ON DELETE CASCADE,
    game_id UUID REFERENCES coachlenz.games(id) ON DELETE SET NULL,
    sport TEXT NOT NULL,
    stats JSONB NOT NULL DEFAULT '{}',
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE coachlenz.player_stats ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass_player_stats" ON coachlenz.player_stats
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================
-- TABLE: practice_plans
-- ============================================================
CREATE TABLE IF NOT EXISTS coachlenz.practice_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES coachlenz.teams(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    title TEXT NOT NULL,
    duration_minutes INTEGER,
    drills JSONB NOT NULL DEFAULT '[]',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE coachlenz.practice_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass_practice_plans" ON coachlenz.practice_plans
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================
-- TABLE: coaches
-- ============================================================
CREATE TABLE IF NOT EXISTS coachlenz.coaches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'assistant' CHECK (role IN ('head','assistant','coordinator')),
    team_ids UUID[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE coachlenz.coaches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass_coaches" ON coachlenz.coaches
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================
-- INDEXES for performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_players_team_id ON coachlenz.players(team_id);
CREATE INDEX IF NOT EXISTS idx_games_team_id ON coachlenz.games(team_id);
CREATE INDEX IF NOT EXISTS idx_games_date ON coachlenz.games(date);
CREATE INDEX IF NOT EXISTS idx_player_stats_player_id ON coachlenz.player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_game_id ON coachlenz.player_stats(game_id);
CREATE INDEX IF NOT EXISTS idx_practice_plans_team_id ON coachlenz.practice_plans(team_id);
CREATE INDEX IF NOT EXISTS idx_practice_plans_date ON coachlenz.practice_plans(date);
