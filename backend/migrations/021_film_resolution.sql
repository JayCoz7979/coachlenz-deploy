-- Capture the ingested film's resolution so we can (a) prefer/verify HD and
-- (b) honestly flag low-res film, which is the ceiling on jersey-number reading
-- (a 360p frame renders a number at ~15px = unreadable; 1080p reads ~2.7x more).
ALTER TABLE games ADD COLUMN IF NOT EXISTS film_width INTEGER;
ALTER TABLE games ADD COLUMN IF NOT EXISTS film_height INTEGER;
