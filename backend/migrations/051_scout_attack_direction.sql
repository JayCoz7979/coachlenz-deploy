-- Possession anchor for basketball. A 20-year analyst never re-reads the jersey every
-- possession; they anchor to which basket a team attacks (constant within a half, flips
-- at the half) and track flow. This stores the scouted team's first-half attacking
-- direction AS SEEN ON THE FILM ('left' | 'right'); the detector then derives every
-- possession deterministically from the direction of attack, flipping at halftime.
-- Null = not set (the engine falls back to auto-anchoring from the majority read).
ALTER TABLE games ADD COLUMN IF NOT EXISTS scout_attack_dir_h1 TEXT;
