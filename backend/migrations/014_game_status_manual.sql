-- The opponent-scouting flows (basketball + football) create a Game shell with
-- status 'manual' to distinguish a hand-charted / CSV-imported scout from a film
-- game. The games_status_check constraint (migration 007) never included 'manual',
-- so every /scout/session and /scout/football/session insert failed with a check
-- violation in production. Add 'manual' to the allowed set.
ALTER TABLE games DROP CONSTRAINT IF EXISTS games_status_check;
ALTER TABLE games ADD CONSTRAINT games_status_check
    CHECK (status IN ('pending','queued','downloading','processing','analyzing','ready','error','manual'));
