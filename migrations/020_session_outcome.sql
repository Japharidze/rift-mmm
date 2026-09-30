-- How a session ended (panel round 2). A player who loves nothing -- or loves
-- only for the people, the world or the memory -- gets no point and no
-- champions, and used to leave no row at all: the most common failure the
-- simulation predicts (~13% on round 1's cards) was invisible to the panel.
-- Now they are stored with the outcome, and the panel report counts them
-- beside unread dimensions.
--
-- A session that later reaches a result (the player went back and picked
-- again) is updated to 'result'; its events keep the history.

alter table quiz_session
    add column outcome text not null default 'result'
        check (outcome in ('result', 'loved_nothing', 'no_gameplay_love')),
    alter column point drop not null,
    alter column dimensions drop not null,
    alter column champions drop not null;
