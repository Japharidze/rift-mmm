-- Champion labels: the ten sub-traits and three aggregates from
-- docs/sub-traits.md, one row per champion x role x label_run.
--
-- Append-only, grouped by label_run (CLAUDE.md, frozen decisions). A
-- re-labelling run inserts a new label_run and a fresh set of champion_label
-- rows; nothing already stored is ever updated. The diff between two runs for
-- the same champion_id/role is drift or a prompt change, and both are things
-- to see, not to overwrite away.

create table label_run (
    id             bigserial primary key,
    prompt_version text not null,   -- constant in r3m.labeling.prompt
    model          text not null,   -- e.g. 'claude-opus-4-6-20260115'
    started_at     timestamptz not null default now(),
    note           text             -- free text: what changed since the last run
);

-- role is champion x role's other half but is not FK'd to champion_role_live:
-- that is a view (Postgres cannot target one with a foreign key), and which
-- roles are "live" shifts as the match sample grows. Whether a role is still
-- above the 30% threshold at label time is an application-level check
-- (r3m.labeling), not a schema constraint.
create table champion_label (
    id             bigserial primary key,
    label_run_id   bigint not null references label_run (id),
    champion_id    text not null references champion (id),
    role           role_t not null,

    -- sub-traits: absolute, independent, 0-1 (docs/sub-traits.md)
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

    -- Aggregates are stored, not a view over the sub-traits: the weighting
    -- that produced them (equal, for the pilot) is a modelling choice that
    -- must stay reproducible from what a run actually output, not recomputed
    -- later under whatever weights the fit against Surnex's placements lands
    -- on (CLAUDE.md, open questions). A weight change is a new label_run.
    micro numeric(3, 2) not null check (micro between 0 and 1),
    meso  numeric(3, 2) not null check (meso between 0 and 1),
    macro numeric(3, 2) not null check (macro between 0 and 1),

    rationale    text,            -- model's free-text justification, kept for review
    raw_response jsonb not null,  -- full structured output, for replay without a re-call
    labelled_at  timestamptz not null default now(),

    unique (label_run_id, champion_id, role)
);

create index champion_label_lookup on champion_label (champion_id, role);
