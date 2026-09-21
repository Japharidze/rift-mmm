-- Match sample: the position distribution that decides champion_role, plus the
-- raw material for the drift signals (win-rate-by-duration, rank-tier spread,
-- deaths). Match data never produces labels — see CLAUDE.md, frozen decisions.
--
-- Rows are kept per participant rather than pre-aggregated so the sample is
-- additive: topping 2k matches up to 5k needs no refetch, a resumed crawl can
-- skip match ids already stored, and share thresholds can be recomputed without
-- another crawl.

create table match (
    match_id     text primary key,            -- e.g. 'EUW1_6543210987'
    platform     text not null,               -- routing value the id came from
    queue_id     integer not null,            -- 420 = ranked solo
    game_version text not null,               -- Riot build string, e.g. '16.18.615.9832'
    -- Data Dragon versions ('16.18.1') and Riot build strings are different
    -- shapes, so major.minor is derived once here instead of in every query.
    patch        text generated always as (
                     split_part(game_version, '.', 1) || '.' ||
                     split_part(game_version, '.', 2)
                 ) stored,
    duration_s   integer not null,
    played_at    timestamptz not null,
    -- Tier of the player this match was discovered through. An approximation of
    -- the lobby's rank, not a per-participant rank: match-v5 does not carry one.
    seed_tier    text not null,
    fetched_at   timestamptz not null default now()
);

create index match_patch on match (patch);

create table match_participant (
    match_id      text not null references match (match_id) on delete cascade,
    puuid         text not null,
    -- Deliberately no foreign key to champion. A match can contain a champion
    -- released after the Data Dragon patch we ingested, and Riot's string id has
    -- differed from Data Dragon's in casing before (FiddleSticks). champion_key
    -- is the stable join: it matches champion.riot_key.
    champion_key  integer not null,
    champion_name text not null,              -- Riot's string id, kept raw
    -- TOP / JUNGLE / MIDDLE / BOTTOM / UTILITY, or '' where Riot could not
    -- assign one (remakes, odd team comps). Kept raw; mapped in the view below.
    team_position text not null,
    win           boolean not null,
    kills         integer not null,
    deaths        integer not null,
    assists       integer not null,
    primary key (match_id, puuid)
);

create index match_participant_champion
    on match_participant (champion_key, team_position);

-- Per-champion role shares. Raw shares only: no threshold is applied here,
-- because where to cut is a decision to make from the distribution, not before
-- seeing it.
create view champion_role_share as
with mapped as (
    select
        p.champion_key,
        case p.team_position
            when 'TOP'     then 'top'
            when 'JUNGLE'  then 'jungle'
            when 'MIDDLE'  then 'mid'
            when 'BOTTOM'  then 'bot'
            when 'UTILITY' then 'support'
        end::role_t as role
    from match_participant p
)
select
    c.id                                                        as champion_id,
    m.role,
    count(*)                                                    as games,
    sum(count(*)) over (partition by c.id)                      as champion_games,
    count(*)::numeric / sum(count(*)) over (partition by c.id)  as share
from mapped m
join champion c on c.riot_key = m.champion_key
where m.role is not null
group by c.id, m.role;
