-- Detection-quality gate, basketball shot-scoped recall. Basketball detection emits
-- many event types per possession (shot/rebound/assist/foul/steal/block/turnover),
-- so the all-event recall does not line up with a scorebook. This is the apples-to-
-- apples number a basketball coach can verify: an admin-confirmed true FIELD-GOAL-
-- ATTEMPT count (made + missed, both teams, from the box score) that the gate
-- compares against detected 'shot' events -> shot recall = detected shots / true FGA.
-- Null (default) means not ground-truthed; the gate omits shot recall for that game.

ALTER TABLE games ADD COLUMN IF NOT EXISTS true_shot_count INTEGER;
