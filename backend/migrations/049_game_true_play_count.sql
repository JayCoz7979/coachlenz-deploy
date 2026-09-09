-- Detection-quality gate: an admin-confirmed TRUE play/event count for a game.
-- When set, the Film Quality gate stops reporting the coach-added-plays FLOOR and
-- reports a real (labeled) recall for that game = auto-detected / true count. This is
-- the only way a recall number on the gate is verified rather than a floor.
-- Null (the default) means "not ground-truthed yet" and the gate falls back to the
-- proxy floor, exactly as before.

ALTER TABLE games ADD COLUMN IF NOT EXISTS true_play_count INTEGER;
