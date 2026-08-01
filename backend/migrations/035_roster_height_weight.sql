-- Player height + weight on the roster. Height is free-text so a coach can enter
-- "6'2" naturally; weight is pounds. Both optional. Feeds the roster and the
-- recruiting profile.
ALTER TABLE roster_players ADD COLUMN IF NOT EXISTS height text;
ALTER TABLE roster_players ADD COLUMN IF NOT EXISTS weight integer;
