-- Replaces the whole `challenges` blob with the fields actually wanted.
-- Storing all ~130 projected to roughly 109 MB at 2k matches; these 13 cost
-- about 1 MB. They validate labels and never produce them (CLAUDE.md), so the
-- breadth was not buying much.
--
-- No denominator column is needed: rates are computed against match.duration_s.
-- All nullable — older matches predate the block, and Riot omits fields that
-- never applied in a given game.

alter table match_participant drop column challenges;

alter table match_participant
    -- micro: execution, and reaction inside a short window
    add column skillshots_hit                 integer,
    add column skillshots_dodged              integer,
    add column skillshots_dodged_small_window integer,
    add column ability_uses                   integer,
    -- macro: vision, objectives, map movement
    add column vision_score_per_minute        real,
    add column control_wards_placed           integer,
    add column turret_plates_taken            integer,
    add column teleport_takedowns             integer,
    add column dragon_takedowns               integer,
    add column baron_takedowns                integer,
    -- meso: fights won against the odds, and moving unseen
    add column outnumbered_kills              integer,
    add column unseen_recalls                 integer,
    add column kill_after_hidden_with_ally    integer;
