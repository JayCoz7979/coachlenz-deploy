-- The Live Game Play Logger creates a Game shell with status 'live' to
-- distinguish a real-time, sideline-charted game from a film game ('ready'),
-- an import ('queued'/'processing'), and a hand-charted scout ('manual').
-- 'live' is not in the games_status_check set (migration 014), so without this
-- every /live/session insert would fail with a check violation in Postgres.
ALTER TABLE games DROP CONSTRAINT IF EXISTS games_status_check;
ALTER TABLE games ADD CONSTRAINT games_status_check
    CHECK (status IN ('pending','queued','downloading','processing','analyzing','ready','error','manual','live'));
