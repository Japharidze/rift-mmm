-- What a Riot account actually plays, one row per fetch (r3m panel-check).
--
-- Kept apart from quiz_session on purpose: mains belong to a player, not to a
-- quiz, and one player can take the quiz several times (Sergi's account is on
-- three sessions, JohnRod's on two). quiz_session.actual_mains (015) stores a
-- copy per session and overwrites it; this table keeps every fetch, dated, so
-- a refetch is a new row and the history survives. Sessions join on the Riot
-- id whenever they need to ("merge later").
--
-- Until 2026-10-01 fetched mains lived only in data/panel-mains.json on one
-- laptop: not in production, not in backups. Those fetches are imported here
-- with source 'cache'.
--
-- riot_key and resolved_key are the ids lowercased with whitespace removed:
-- what testers type varies ("JohnRod #warud", "Koekamundo" with no tag), and a
-- join on either key finds the account. No puuid: nothing here needs it.

create table riot_mains (
    id           bigserial primary key,
    riot_id      text not null,                 -- as the tester typed it
    riot_key     text not null,                 -- normalised typed id
    resolved     text,                          -- Name#TAG the API resolved it to
    resolved_key text,                          -- normalised resolved id
    tag_guessed  boolean not null default false,
    fetched_at   timestamptz not null,
    games        integer not null,              -- placed games counted
    mains        jsonb not null,                -- [{champion_id, role, games}], most played first
    source       text not null check (source in ('fetched', 'cache')),
    unique (riot_key, fetched_at)
);

create index riot_mains_riot_key on riot_mains (riot_key);
create index riot_mains_resolved_key on riot_mains (resolved_key);
