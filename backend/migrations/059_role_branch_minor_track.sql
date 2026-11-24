-- Rename the stored minor branch. player_hold was the earlier name.
-- Readers also accept player_hold. Do not run this by hand against production.
-- The migrator ignores the matching .down.sql file.

UPDATE marketing_leads
    SET role_branch = 'minor_track'
    WHERE role_branch = 'player_hold';
