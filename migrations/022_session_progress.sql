-- Drop-off (panel round 2 on the longer build). A session used to be stored
-- only when it reached a result or "not enough to go on", so everyone who gave
-- up mid-quiz left nothing -- and at 70 cards plus follow-ups, abandonment is
-- the main risk to the round.
--
-- Now a row is created at the first answer with outcome 'in_progress' and
-- updated at every step, the last one reached in last_step:
--   round-1..round-5    a round of cards on screen
--   loves-1..loves-5    "what made it stick?" after that round
--   why                 the follow-up about a dislike
--   fill                a single card for an unread dimension
--   deep                a deep-dive question
--   compare             a comparison pair
--   nothing             "not enough to go on"
--   rating              the result shown, "feel right?" not yet answered
--   rated               answered or skipped
-- A row still 'in_progress' long after updated_at is an abandoned session.
-- Reaching a result turns it into 'result' as before; the headline counts
-- only those.

alter table quiz_session drop constraint quiz_session_outcome_check;
alter table quiz_session
    add constraint quiz_session_outcome_check
        check (outcome in ('result', 'loved_nothing', 'no_gameplay_love', 'in_progress')),
    add column last_step text,
    add column updated_at timestamptz not null default now();
