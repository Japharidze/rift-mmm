-- Slice 1 of the quiz chain (docs/quiz-chain.md §3, §5): stop counting the
-- wrong things.
--
-- game.bias: how easily a game can be loved without engaging its demand --
-- low / medium / high, hand-judged in bank/bias.yaml, loaded by
-- `r3m bank-import`. A high love counts as weak evidence until the player says
-- it was the gameplay. Null for games not rated yet, which counts as no
-- discount: an unrated game gets no prior rather than an invented one.
--
-- quiz_session.verdicts: every recognised game and what was said about it --
-- loved / fine / disliked. `loved` and `disliked` stay as they were, so earlier
-- sessions and the comparison pass read unchanged; "fine" exists only here,
-- because it is recognition without taste and belongs in neither list.
--
-- quiz_session.reasons: the one-tap answers to "what made it stick?" and
-- "what put you off?", keyed by game. Stored as given, so a later analysis can
-- measure how much of the loves were about something other than the gameplay
-- (docs/quiz-chain.md §8) -- the share this slice exists to find out.

alter table game
    add column bias text check (bias in ('low', 'medium', 'high'));

alter table quiz_session
    add column verdicts jsonb,
    add column reasons jsonb;
