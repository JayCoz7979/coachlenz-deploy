-- Threads (discussion threads attached to games/clips/reports)
CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title TEXT,
    context_type TEXT CHECK (context_type IN ('game','clip','report','general')),
    context_id UUID,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE thread_members (
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, user_id)
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id),
    body TEXT NOT NULL,
    parent_id UUID REFERENCES messages(id),
    edited_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE message_mentions (
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (message_id, user_id)
);

CREATE TABLE thread_reads (
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    last_read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, user_id)
);

-- Playlists
CREATE TABLE playlists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    created_by UUID REFERENCES users(id),
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE playlist_clips (
    playlist_id UUID NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    PRIMARY KEY (playlist_id, clip_id)
);

-- Clip Assignments
CREATE TABLE clip_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    assigned_to UUID REFERENCES users(id),
    assigned_by UUID REFERENCES users(id),
    note TEXT,
    due_date DATE,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Film Packages (shareable bundles for opponents/scouts)
CREATE TABLE film_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT,
    clip_ids UUID[] NOT NULL DEFAULT '{}',
    share_token TEXT UNIQUE NOT NULL DEFAULT gen_random_uuid()::TEXT,
    expires_at TIMESTAMPTZ,
    view_count INTEGER NOT NULL DEFAULT 0,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Notifications
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    data JSONB DEFAULT '{}',
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_threads_org ON threads(organization_id);
CREATE INDEX idx_messages_thread ON messages(thread_id);
CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_notifications_unread ON notifications(user_id) WHERE read_at IS NULL;
CREATE INDEX idx_film_packages_token ON film_packages(share_token);
