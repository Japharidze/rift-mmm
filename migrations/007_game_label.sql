-- The game half of the MMM space.
--
-- Games are hand-curated rather than ingested: there is no Data Dragon for
-- them. anchors/games.yaml is the source of the anchor set; the wider quiz bank
-- lands here too once it exists.
--
-- Labels reuse label_run. A run's prompt_version distinguishes the two rubrics
-- ('v3' for champions, 'games-v1' here), so one table keeps the whole labelling
-- history in one place rather than forking it.

create table game (
    id         text primary key,        -- slug, e.g. 'stardew-valley'
    name       text not null,
    -- Set only where a title's modes genuinely differ in MMM, in which case
    -- each mode is its own row (docs/3m-model.md: chess-blitz and
    -- chess-classical are two items). Null means "as commonly played".
    mode       text,
    is_anchor  boolean not null default false,
    added_at   timestamptz not null default now()
);

create table game_label (
    id           bigserial primary key,
    label_run_id bigint not null references label_run (id),
    game_id      text not null references game (id),

    micro_precision     numeric(3, 2) not null check (micro_precision between 0 and 1),
    micro_execution     numeric(3, 2) not null check (micro_execution between 0 and 1),
    micro_cheat         numeric(3, 2) not null check (micro_cheat between 0 and 1),

    meso_deception      numeric(3, 2) not null check (meso_deception between 0 and 1),
    meso_prediction     numeric(3, 2) not null check (meso_prediction between 0 and 1),
    meso_exploitation   numeric(3, 2) not null check (meso_exploitation between 0 and 1),
    meso_cheat          numeric(3, 2) not null check (meso_cheat between 0 and 1),

    macro_routing       numeric(3, 2) not null check (macro_routing between 0 and 1),
    macro_win_condition numeric(3, 2) not null check (macro_win_condition between 0 and 1),
    macro_cheat         numeric(3, 2) not null check (macro_cheat between 0 and 1),

    micro numeric(3, 2) not null check (micro between 0 and 1),
    meso  numeric(3, 2) not null check (meso between 0 and 1),
    macro numeric(3, 2) not null check (macro between 0 and 1),

    rationale    text,
    raw_response jsonb not null,
    labelled_at  timestamptz not null default now(),

    unique (label_run_id, game_id)
);

create index game_label_lookup on game_label (game_id);
