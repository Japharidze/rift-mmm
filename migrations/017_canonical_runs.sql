-- Which label runs are served: an explicit, per-database canonical set.
--
-- Until now the labels in use were "the newest label per item within the
-- widest-coverage prompt version". That silently turns into "whatever ran
-- last" once several regimes share a prompt version -- Opus 5 at default
-- effort, Opus 5 at low effort (run 23), and the Opus 5.5 pilots all label
-- games-v2 and v3 -- which is exactly the regime mixing the one-model rule
-- forbids. Locally, run 23 was being served the day this was written.
--
-- A flag on label_run rather than run ids in code: a relabel run against
-- production gets different ids there than locally, and the set must be
-- chosen per database. `r3m canonical` changes it, and refuses a set that
-- mixes models or effort levels.
--
-- The validated set to start: label_run 9 + 10 (champions, v3, Opus 5; 10
-- fills the 8 rows 9 lost) and 17 (games-v2, Opus 5, all 50 games). Guarded by
-- prompt version, so a database whose ids differ flags nothing rather than the
-- wrong run.

alter table label_run add column canonical boolean not null default false;

update label_run set canonical = true
 where (id in (9, 10) and prompt_version = 'v3')
    or (id = 17 and prompt_version = 'games-v2');
