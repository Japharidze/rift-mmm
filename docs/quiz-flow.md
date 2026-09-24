# Quiz flow — grid, fill, specify

Status: built. `quiz.grid`, `quiz.fill_item`, `quiz.sharpen`,
`quiz.apply_comparisons`; endpoints `/quiz/grid`, `/quiz/estimate`,
`/quiz/fill`, `/quiz/sharpen`, and `comparisons` on `/quiz/result`; staged
frontend in `web/src/App.jsx`. The estimator's core (`quiz.estimate`) and the
matcher (`scoring.py`) are unchanged by it -- this is an interaction model over
the same measurement.

## Why three stages

The first quiz was one game name, three buttons, repeat. It works and it reads
as an interrogation: nothing to look at, no sense of progress toward anything,
and no reason the fifth question exists rather than stopping at the fourth.
Density is what a single card cannot supply, but density alone loses the
adaptivity that makes the last few questions worth asking.

The stages split that. Each one does a job the others are bad at.

    1. grid     general    broad strokes, fast, nothing adaptive lost
    2. fill     targeted   only the dimensions the grid left unread
    3. specify  refining   sharpen the axis that changes the answer

## Stage 1 — grid

24-30 cards on one screen, two passes: "tap everything you loved", then the
same grid for "anything here you bounced off". The three-way answer survives
(loved / didn't stick / never played) because silence in the second pass is
never-played, which is what it already means.

This replaces the three-item opener, which was hardcoded and identical for
every user, so nothing adaptive is given up: those items were never chosen
adaptively in the first place.

**Size.** 24-30 of 43, not 16. The instinct to show fewer comes from
one-at-a-time thinking, where every served item costs a decision. A grid is
scanned, not answered; an unrecognised card costs a glance. Showing more
therefore buys coverage of the space almost for free, and at 30 the
hand-curation problem mostly dissolves because you are nearly serving the whole
bank.

**Which cards.** Greedy farthest-point over the bank: take the most extreme
game, then repeatedly take whichever is furthest from everything already
picked. It covers the poles by construction rather than by judgement.

Cover art breaks near-ties (`ART_SLACK`). Distance alone concentrated the art
gap into the grid: the poles are disproportionately the Nintendo, Blizzard and
mobile titles Steam does not carry, so 12 of 28 cards came out text-only while
the games it discarded mostly had covers. Preferring art among candidates
within 85% of the best spread takes that to 10 of 28. The remaining ten are the
sole occupants of their regions -- displacing them would cost coverage, so they
stay.

Pure farthest-point puts obscure extremes first and leaves the middle of the
space for last -- and the middle of the space is where the mainstream lives. At
n=30 the leftovers are Elden Ring, League, Valorant, osu!, Tekken, Hades,
Smash. That is the right way round: the grid absorbs the obscure items, where a
card costs a glance, and stage 2 inherits the recognisable ones, where an item
costs a decision.

Curation still beats the algorithm on recognisability, and there is no reach
signal in the data yet to decide it. Until there is, the list is hand-built
with farthest-point as a coverage check, not a generator -- a temporary
artifact, and better labelled as one than quietly shipped as principle.

## Stage 2 — fill

Single cards, the existing interaction. Nearly free: `next_item` already picks
the most informative unserved game. The change is to restrict the pool to games
informative on the dimensions still unread, and to stop as soon as `NEEDED` is
met per axis rather than running to `MAX_ITEMS`.

Zero to four items, often zero. Variable length for an honest reason, and the
copy should say it -- "we can read how you execute and how you read people, two
more on the planning side" -- which turns the phase from more-of-the-same into
a stated gap being closed.

`NEEDED` rose from 2 to 3 when the grid replaced the three-item opener. A grid
hands over many more picks than a handful of single cards did, and at 2 a
typical grid cleared every dimension outright -- so this stage almost never
ran, and an axis was called read on two observations. Measured over random
picks from the grid, the fill stage now runs for 84% of five-pick sessions and
32% of eight-pick ones; someone who tapped twelve games has genuinely been read
and skips it.

`informative` is also weighted by verdict -- a loved game counts 1, a disliked
one `DISLIKE_WEIGHT`. A dislike contributing half an observation to the value
but a whole one to "we have read this" was inconsistent, and the grid made it
matter: a handful of cheap second-pass taps could declare a dimension read on
evidence the estimator itself only half trusts.

## Stage 3 — specify

Pairwise, **after a provisional result**, offered rather than imposed: "here
are your five -- want to sharpen it?" Two reasons. A user who leaves still
leaves with an answer, and "sharpen this" gives the comparison stakes that a
fourth anonymous question phase does not have.

**Contrastive pairs only.** Two games matched on the dimensions already read
and split on the one being sharpened. The comparison is then a clean read on
that axis because everything else is controlled: "Factorio or Minecraft
creative" isolates macro -- both are build-something-alone games, they diverge
on whether there is a system to optimise. A newcomer can answer that without
knowing what macro means, which is the whole trick.

Thresholds: split >= 0.35 on the target axis, <= 0.15 on the other two.

**Drawn from everything recognised**, not the bank, and not the loved set
alone. Restricting the pool to loved games looked right -- "you liked both,
which more" is the cleanest form of the question -- but the grid broke it. A
second pass asking what you bounced off makes dislikes cheap to tap and people
mark many; those count toward a dimension being read, which closes the fill
stage, while a loved-only pool stays tiny and closes this one. Measured at
three loved and eight disliked, the fill stage fired 6% of sessions and a pair
existed in 24%: both stages vanished for anyone who used the second pass the
way it invites. Drawing from every answered game takes the pair to 100% there,
and the question is worded from the verdicts -- "which would you go back to"
rather than "which did you like more" when either was a bounce. This removes the failure mode that
otherwise sinks pairwise: serve two games, the user has played neither, and the
screen bought nothing. A verdict cannot fail that way -- never-played is a valid
answer. A comparison can. Both cards being already-loved makes it impossible.

It is not double-counting, provided the answer updates the point relatively
rather than landing as a fresh absolute observation. "You loved both -- which
more" is information the three-way verdict had no way to express.

**Which axis.** Perturb the estimate by +/-0.05 on each dimension independently
and re-run the match; whichever reorders the top five most is the one worth a
question. The 0.05 is set by the space, not chosen: median nearest-neighbour
distance between champions is 0.051 and `CLOSE` is 0.10.

This asks "which uncertainty actually changes what I would tell you", which is
the only question worth spending a user's attention on. Largest uncertainty and
largest consequence are different axes, and it is the second one that matters.

**Degrade by disappearing.** If no contrastive pair exists on the chosen axis
inside the loved set, try the next axis; if none at all, do not offer the
refinement. The provisional result is already complete -- which is the reason
stage 3 sits after it.

## The cap on stage 3, as a trade

Cumulative displacement from all of stage 3 is bounded to roughly the width of
the `CLOSE` band, so it sharpens rather than relocates. Per-pair caps do not
achieve this; three permitted pairs can walk the point anywhere.

The pull per comparison has to be set against that cap rather than picked for
its own sake. At half the gap to the winner, a *single* comparison saturated
the cap -- pairs are contrastive by construction, so the winner is always far
from the current estimate -- which made every answer move the same distance and
left the cap as the only live parameter. At a fifth, one answer moves about
0.06, two in agreement reach the 0.10 ceiling, and contradictory answers
cancel. Measured, not assumed.

Record it as a trade, not a parameter. A comparison genuinely carries more
information than a verdict, so capping its influence below what that
information warrants is deliberate underweighting of the best evidence in the
pipeline. It is the right call *here* because the user is watching a result
they have already been shown, and stability beats marginal accuracy when the
list is visibly rearranging under them. That justification is situational:
**if stage 3 ever runs before the result is shown, the cap comes off.**

## Progress

A live readout of the current estimate, settling as answers arrive.
`N answered` has no denominator, because the stop condition is adaptive and
there is no honest total -- so show movement instead of a fraction.

**A marker on an axis, not a filling bar.** The three numbers are a position in
a space, not a score out of one. As a bar, picking a game you loved can visibly
lower all three -- the estimate is a mean, so a low-macro pick pulls macro
down -- and a shrinking bar reads as a penalty for answering honestly. Low
macro is a taste for games without a planning layer. A marker that slides
carries no more-is-better implication, and the caption says so outright.

An unread dimension shows no marker rather than one at its provisional value:
a confident-looking position for something not yet seen is the imputation the
model refuses to make.

## Showing that stage 3 did something

The cap keeps the point from relocating, on purpose, so a comparison's real
effect lands at ranks three to five while the top one or two hold. That is the
design working, and it is invisible -- which reads as a button that does
nothing. Champions the last comparison brought into the list are marked, so the
effect is pointed at rather than left to be noticed.

## What this needs that does not exist yet

**A bigger bank, aimed at one pole.** Stage 3 needs a contrastive pair inside
one person's loved set, which is a far tighter requirement than inside the
bank. Simulated over random six-game loved sets: 77% contain some usable pair,
but only 31.5% contain a macro pair -- and that is optimistic, because a real
loved set is taste-clustered, matched on all three axes, which is exactly what
makes a split on one axis rare. Macro is the axis most worth sharpening (Gate
2: load-bearing and worst-measured) and the one stage 3 can least often reach.

The gap is the low-macro pole: 6 games of 43. Wanted are games high on micro or
meso, low on macro, with high recognition -- short loop, no planning layer.
Candidates: Overcooked, Lethal Company, Vampire Survivors, Trackmania, and Slay
the Spire as the high-macro contrast partner.

Two of the candidates are modes rather than titles -- Rocket League casual,
Counter-Strike deathmatch. `game.mode` exists for this and is null on all 43
rows. Same title, different mode, different point, no migration.

**A reach signal**, to decide the grid by recognisability rather than by hand.
Bimodal playtime beats review score: it separates games people bounce off from
games nobody tried, and that distinction is the quiz's whole subject.


## A loved game's low coordinates are not evidence — found 2026-09-24

The first test against a known taste, and the quiz got it backwards.

    champions Sergi plays or likes (19)   0.68 / 0.60 / 0.57
    his quiz result                       0.34 / 0.32 / 0.69
    distance                              0.457   (CLOSE is 0.10)

He loved Valheim, Factorio and Hades. The estimator is arithmetically right --
those three alone give 0.44 / 0.20 / 0.72, and his dislikes moved it a little
further. The error lives almost entirely in **meso: 0.20 against 0.60**.

All three games are single-player or co-op. None has a human opponent, so all
three score 0.12-0.25 on a dimension defined as "reacting to the unpredictable
behaviour of people". Meanwhile he mains Thresh, Bard and Zilean, three of the
most meso-heavy champions in the game.

**The defect: loving a low-meso game is treated as evidence of disliking meso.**
It is evidence of liking that game. Loving Factorio says "I like planning"
loudly and says nothing about mind-games, because the question never arose --
Factorio has no opponent to outguess. But the estimator averages all three
coordinates of every loved game, so Factorio's 0.12 lands as a positive vote
for this player being low-meso.

`INFORMATIVE` makes it worse. The test is |x - 0.5| >= 0.25, so Factorio at
0.12 counts as strongly informative about meso, and the result showed a
confident 0.32 rather than "not enough to tell". **The frozen rule says an
unread dimension is reported, never imputed. Here it imputed and called it
read.**

This is the problem the original upper-half mean was reaching for. It was
replaced by a plain weighted mean once negative evidence existed, on the
grounds that dislikes removed the ambiguity. They do not: his dislikes were
not the problem, his loves were over-read.

The missing asymmetry: **a high coordinate in a loved game is strong evidence;
a low one is weak or none.** How to express that is a modelling decision and
is not decided here.

Sergi's call, 2026-09-24: **expand the bank first.** The three games he loved
were all builders because the grid's low-macro and PvP-light regions are what
they are; a wider bank is a precondition for testing any change to how loved
games load.
