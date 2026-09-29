-- Panel round 2 as a benchmark, not a one-shot test (docs/quiz-chain.md §8).
-- Any later estimator -- triangulation, a new dislike rule, sub-trait matching
-- -- must be able to re-score round 2's real players offline, so a session
-- keeps what happened, not only what this build concluded from it.
--
-- quiz_session.events: the raw answer log, in order, from the client. Every
-- round and the cards it showed, every verdict set or changed, every reason
-- asked for and what was answered (or skipped), every fill card, every
-- comparison pair and its pick, and the result being shown. Times are
-- milliseconds since the quiz started.
--
-- quiz_session.build: what produced the stored result -- commit, serving mode,
-- the label runs behind the game and champion points, and the evidence
-- constants. Prompt versions alone cannot tell builds apart: v3 and games-v2
-- were relabelled on a different model (2026-09-29) under the same names.
--
-- quiz_session.feels_right: "do these champions feel right?", asked about the
-- champions before the reading of the player is shown (CLAUDE.md, frozen).

alter table quiz_session
    add column events jsonb,
    add column build jsonb,
    add column feels_right text check (feels_right in ('yes', 'partly', 'no'));
