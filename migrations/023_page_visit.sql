-- The top of the funnel: visits -> started -> finished. A session row starts at
-- the first answer (022), so someone who opens the page and leaves before
-- tapping a card was invisible -- often the biggest drop of all.
--
-- One row per page load, sent by the page itself (so crawlers and the
-- healthcheck, which never run the page's script, are not counted; reloads
-- are). Deliberately nothing about the visitor: no IP, no user agent, no link
-- to a session. Only when, and which build was serving.

create table page_visit (
    id         bigserial primary key,
    created_at timestamptz not null default now(),
    serving    text not null
);
