-- Cover art and release year, so a quiz card is a recognition cue rather than
-- a memory test. A bare title asks the user to recall something cold, and
-- misrecognition is silent: someone confusing two similar titles answers
-- confidently and wrong.
--
-- Partial coverage on purpose. Steam has about half the bank and misses the
-- Nintendo, Blizzard, Riot and mobile titles — which are among the most
-- recognisable things on the list, so a text card for Mario Kart costs little
-- while a cover for Factorio earns a lot. Recognition is per item; there is no
-- reason to keep every card weak while waiting for a second source.
--
-- year is nullable and stays null for series (Street Fighter, Tekken, Mario
-- Kart): a single year for a franchise would be a confident wrong answer, the
-- exact failure this column exists to prevent.
alter table game
    add column steam_appid integer,
    add column release_year integer;
