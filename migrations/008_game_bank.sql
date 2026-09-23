-- Whether a game is worth asking a user about.
--
-- Separate from whether it is a good anchor, because those are different jobs.
-- Rock-paper-scissors anchors the meso pole perfectly and is a useless quiz
-- item; nobody lists it as a game they play. anchors/games.yaml carries the
-- flag, and this column is where the quiz reads it.
alter table game add column in_bank boolean not null default true;
