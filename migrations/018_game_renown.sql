-- How likely a player in the segment (14-30, EUNE, PC) is to recognise a game:
-- the first factor of a card's value (docs/quiz-chain.md §4, "a card is a
-- question": value = P(recognised) x expected change in belief).
--
-- reach: Steam lifetime reviews, or recommendations where review stats lag --
-- the number the Steam portion of the bank was ranked by (bank/steam.yaml).
-- Null for games off Steam.
-- renown: a hand tier for the games Steam cannot rank (bank/hand.yaml):
-- universal / wide / niche. Null for Steam games and deep entries.
--
-- Both are priors, not measurements of this segment. Panel tap rates correct
-- them where the panel has shown a card.

alter table game
    add column reach bigint,
    add column renown text check (renown in ('universal', 'wide', 'niche'));
