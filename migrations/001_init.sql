-- Champion ingestion: Data Dragon material and the primary-role gate.
-- Labels land in a later migration, once the prompt wording is frozen.

create table patch (
    version     text primary key,           -- Data Dragon version, e.g. '16.18.1'
    ingested_at timestamptz not null default now()
);

create table champion (
    id          text primary key,           -- Data Dragon id, e.g. 'Karthus'
    riot_key    integer not null unique,    -- numeric key, e.g. 30
    name        text not null,
    title       text not null,
    -- Riot class tags. Stored for validation only; never rendered into the
    -- labelling prompt (see CLAUDE.md, frozen decisions).
    tags        text[] not null,
    partype     text not null,              -- resource: Mana, Energy, None, ...
    first_patch text not null references patch (version),
    last_patch  text not null references patch (version)
);

-- One row per champion per patch. `raw` is kept so a revised text cleaner can
-- be re-run without refetching a patch that may have rotated off the CDN.
create table champion_patch (
    champion_id   text not null references champion (id),
    patch_version text not null references patch (version),
    raw           jsonb not null,           -- full Data Dragon entry
    kit_text      text not null,            -- cleaned passive + QWER prose
    primary key (champion_id, patch_version)
);

create type role_t as enum ('top', 'jungle', 'mid', 'bot', 'support');

-- Today: exactly one primary row per champion, seeded from a fixture.
-- The table shape allows more, so Gate 1 can add secondary roles without a
-- migration. `source` records provenance: 'fixture' now, 'match_data' later.
create table champion_role (
    id          bigserial primary key,
    champion_id text not null references champion (id),
    role        role_t not null,
    is_primary  boolean not null default true,
    source      text not null,
    source_at   timestamptz not null default now(),
    unique (champion_id, role)
);

create unique index champion_role_one_primary
    on champion_role (champion_id)
    where is_primary;
