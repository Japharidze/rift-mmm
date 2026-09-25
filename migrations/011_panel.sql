-- One row per quiz someone actually took.
--
-- The point of the panel is not feedback in the abstract: it is the check that
-- was run by hand once, on one person, and found the quiz reading him as
-- low-meso while he mained Thresh and Bard (docs/quiz-flow.md). Automating
-- that needs three things stored together -- what they tapped, what the quiz
-- concluded, and who they are in game -- so a later pass can fetch their real
-- champion pool and measure the gap.
--
-- riot_id is optional and asked for separately, after the result, with its
-- purpose stated. Someone who declines still contributes everything except
-- that comparison.
--
-- Prompt versions are stored because the labels move: an analysis run next
-- month must know whether a session was scored against v3 or something later,
-- or it will compare a point to a space that no longer exists.

create table quiz_session (
    id              bigserial primary key,
    created_at      timestamptz not null default now(),

    -- what they were shown and what they said
    served          text[] not null,
    loved           text[] not null,
    disliked        text[] not null,
    comparisons     jsonb not null default '[]'::jsonb,

    -- what the quiz concluded, stored rather than recomputed: the estimator
    -- changes, and a session must keep meaning what it meant at the time
    point           numeric(3, 2)[] not null,
    dimensions      jsonb not null,   -- per dimension: value, opportunity, read
    champions       jsonb not null,   -- what was actually put in front of them

    champion_prompt_version text not null,
    game_prompt_version     text not null,

    -- supplied afterwards, both optional
    riot_id         text,             -- gameName#tagLine
    riot_region     text,
    feedback        text,

    -- filled by the offline comparison pass, null until then
    checked_at      timestamptz,
    actual_point    numeric(3, 2)[],  -- centroid of the champions they really play
    actual_games    integer           -- how many of their matches it came from
);

create index quiz_session_pending on quiz_session (created_at)
    where riot_id is not null and checked_at is null;
