-- Two tiers of game, because a wide bank and an eclectic first screen are
-- different things.
--
-- `deck` is the top list: one entry per game, spread across genres, the pool
-- the first screen draws from. `deep` holds what a deck entry opens into --
-- modes whose point genuinely differs (chess blitz vs classical, Texas hold'em
-- vs Omaha, Minecraft Bedwars) and platforms whose point depends entirely on
-- what is played inside them (Roblox, Garry's Mod). They serve comparisons and
-- deep dives after a deck pick, not the first screen.
--
-- Sequels and re-releases are neither: Dark Souls II and III sit on the same
-- point, so a deep dive between them teaches nothing. They are collapsed to one
-- deck entry before import (r3m.bank) rather than stored as variants.
--
-- parent_id links a deep entry to the deck entry it belongs under. A platform
-- has no parent; its modes point at it.

alter table game
    add column tier text not null default 'deck' check (tier in ('deck', 'deep')),
    add column parent_id text references game (id);

create index game_parent on game (parent_id) where parent_id is not null;
