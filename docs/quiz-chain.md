# Quiz chain — adaptive placement inside the MMM space

Status: design, not built. Brainstormed 2026-09-27/28; every claim below about
the code or the data was checked against the repo on 2026-09-28, and where the
brainstorm was wrong the correction is stated in place. Supersedes the verdict
semantics and the stage-1 grid of `docs/quiz-flow.md`; the fill and sharpen
machinery there is generalised here, not replaced.

## 1. Goal

A deep, personalised, high-precision placement of a player — entirely inside
the MMM space. No psychology outside gaming, no fourth dimension. Quizzes differ
between players in which games they see, how many questions they get, and which
question types. Target length: 2-3 minutes for a newcomer.

## 2. Resolution: the ten sub-traits

**Decision (CLAUDE.md):** matching may use the ten sub-traits as a finer
resolution of the three dimensions; nothing outside them surfaces in matching
or UI.

Why it is legitimate: the sub-traits *are* the three dimensions, decomposed
(`docs/sub-traits.md`). Two players who are both "high meso" can want different
champions.

### What the labels actually support (measured 2026-09-28)

**The meso split is real, but it is prediction versus the rest.** Across the 196
production rows (v3, label_run 9+10), meso_deception and meso_prediction
correlate +0.11. The other three meso items cluster: deception-exploitation
+0.72, exploitation-cheat +0.82. So the finer meso axis the labels support is
prediction against {deception, exploitation, cheat}.

Its two ends are not "reader versus bluffer" in the sense the brainstorm used.
Thresh (deception 0.85, prediction 0.80) and Bard (0.82 / 0.85) sit high on
*both*, like Shaco and Neeko (0.98 / 0.72), so they do not illustrate the split.
The champions that do:

    prediction end  Brand sup, Ezreal, Karthus jg, Ashe, Cho'Gath jg   aim where they will be
    trio end        Evelynn, Kha'Zix, Wukong jg, Rengar, Jax           hide what you intend

That matches the v3 wording — prediction is committing before the enemy shows
(slow projectiles, zones, traps) — so the axis reads as *anticipating movement*
against *concealing intent*.

**Sub-trait noise, champion side.** v10 (label_run 21-22) kept v3's micro and
meso wording, so the 93 champion×role rows labelled by both are a clean
test-retest:

    item               mean |diff|   noise / roster spread
    micro_precision       0.024           0.12
    micro_execution       0.030           0.15
    micro_cheat           0.039           0.18
    meso_deception        0.035           0.16
    meso_prediction       0.034           0.20
    meso_exploitation     0.040           0.29
    meso_cheat            0.050           0.32
    (micro aggregate      0.028           0.15)
    (meso aggregate       0.030           0.23)

micro_precision, meso_deception and meso_prediction are usable at sub-trait
resolution. meso_exploitation and meso_cheat are noisier than the aggregate they
feed — as sub-traits they add noise, not resolution.

**Macro sub-traits are not usable.** `docs/sub-traits.md` ("What this
settles"): only routing registers with external sources. Production macro is v3,
whose middle item is win_condition, the one found anti-correlated with the
podcast source (-0.33). No macro test-retest is possible (the wording changed
v3 -> v10).

**Game side: the contrasts are reachable, meso only half as well.** Game
labels are stable (games-v1 vs v2, run 15 vs 17, micro/meso wording unchanged:
noise 0.03-0.07 of spread). Across *all* games, sibling sub-traits correlate
+0.89 to +0.92, which first read as "picks cannot place anyone on a split". That
was an artefact: games either have a dimension or lack it (osu! meso 0.02/0.20,
CS2 0.90/0.90). The fair measure is the contrast among games that *have* the
dimension (>= 0.5):

    contrast                 champions (n)     games (n)
    precision - execution    sd 0.21 (140)     sd 0.19 (28)    games carry it fully
    prediction - deception   sd 0.27 (138)     sd 0.15 (21)    games carry about half

Directions are right at the extremes: aim trainers precision 1.00 / execution
0.80, Tekken 0.80 / 0.92; Liar's Bar and Among Us deception over prediction;
rock-paper-scissors, chess and Hearthstone the reverse. So game picks place a
player on the micro split directly and on the meso split weakly -- deep dives
(§3 step 4) and why-answers (§5) are what strengthen the meso one. The 276
unlabelled bank games raise both n's; re-measure once they are labelled.

### Which sub-traits enter matching (decided on this analysis, 2026-09-28)

A sub-trait adds precision only if it is reliable (test-retest), distinct (not
repeating its siblings: 1 - R² on them, champion side), and reachable (something
in the quiz can place a player on it).

    sub-trait          noise   distinct   verdict
    micro_precision    0.12    0.33       in, as one end of the micro split
    micro_execution    0.15    0.35       in, the other end
    micro_cheat        0.18    0.17       out: the cheat test restated, least distinct
    meso_deception     0.16    0.47       in, one end of the meso split
    meso_prediction    0.20    0.83       in, the other end
    meso_exploitation  0.29    0.23       out: noisy, overlaps deception (+0.72)
    meso_cheat         0.32    0.32       out: noisiest, the cheat test restated
    macro_*            n/a     -          out: only routing registers externally

Matching therefore uses the three dimensions plus **two contrasts**: micro
precision vs execution, and meso prediction vs concealment. Each contrast
counts in proportion to how well the player's position on it was read; unread,
it contributes nothing and the match falls back to the dimensions -- the rule
above, applied per contrast.

**Macro weighting -- a recommendation, not a decision.** Against the 19 tight
champion anchors, routing alone correlates +0.61 with Surnex's macro, the
production aggregate +0.49, win_condition alone +0.25. Weighting macro toward
routing would improve the axis Gate 2 called load-bearing and least verified,
with no relabel. CLAUDE.md keeps weights an open question, so this waits for a
decision (§9) -- and for the comparison pass to have enough players to test
it, since 19 anchors plus three players cannot settle it either.

**Condition on shipping it (Attribution).** `docs/sub-traits.md` ("What this
settles") already set the terms: weighting toward the only component that
measures is a fit against evidence, *not* a redefinition, and must be recorded
in plain words as a measurement limitation. Whichever slice ships it writes, in
CLAUDE.md and sub-traits.md: *this pipeline can only see routing in a
champion's kit, so macro is measured through routing; that is a limit of the
measurement, not a claim that Surnex's macro is routing.* Without that
sentence the weighting quietly edits Surnex's model.

**Surnex's before/after axis** (`docs/3m-model.md`, attention in time:
anticipate/react, suspect/recognise, strategise/calculate) is a within-model
axis from the source itself, but no sub-trait is defined along it. Using it
means new labels, so it is out of scope until a prompt version adds it.

**Honest-output rule.** Precision is capped by label quality. The result says
where resolution is real (the micro split; the meso split, more so once deep
dives feed it) and where it is not (macro, beyond its aggregate). An
unread sub-trait falls back to its dimension's aggregate and is reported as
such — the sub-trait version of "reported, never imputed".

## 3. The chain

1. **Recognition sweep.** Adaptive rounds of ~12 cards. Tap the ones you have
   played, then **"the rest I haven't played"** -- one tap that makes never-played
   a positive answer for the whole round, instead of silence and instead of a
   tap per card. Search box as a fallback.
2. **Verdicts on recognised games only:** loved / fine / didn't like. "Fine"
   carries no taste weight and does not count toward a dimension being read; it
   does count as recognised, which is the recognition data §7 needs.
3. **Why** — for dislikes and for loves (§5).
4. **Deep dives** (Type 2) into loved games that have deep-tier entries.
5. **Provisional result, then sharpening.**
6. **Stop on stability**, not on a count (§4).

### What changes from quiz-flow.md, and it is a reversal, not a bug fix

The brainstorm read the current "meh" handling as a bug. It is a documented
decision. `docs/quiz-flow.md` stage 1 defines the grid's second pass ("anything
here you bounced off") and the fill verdict "Didn't stick" (`App.jsx` VERDICTS,
`meh`) as a **rejection** at `DISLIKE_WEIGHT` 0.5, and makes **silence mean
never-played**. There is no neutral answer at all: a player who felt nothing
either skips (recorded as never played) or taps "Didn't stick" (recorded as a
dislike). Both are wrong, which is the case for the change — but it overturns
two written decisions:

- silence = never played -> never-played is a positive answer;
- didn't stick = dislike -> "fine" is its own verdict at near-zero weight,
  distinct from "didn't like".

quiz-flow.md's pairing logic (comparisons drawn from everything recognised,
worded from the verdicts) still holds and carries over.

### Genre is a fallback, never the router

**Decision (CLAUDE.md).** Genre questions serve only an unread dimension or a
player who recognises nothing. Surnex's first video opens by arguing genre
labels fail (`docs/transcripts/01-cheat-test.md`, 0:16; `docs/3m-model.md`:
"Genre labels don't tell you which of these a game demands"). Routing by genre
would build the product on what the model exists to replace.

Data gap: `game.mode` is null for every row and only the Steam portion of the
bank carries a genre bucket (`bank/steam.yaml`); the 70 hand entries have none.
The fallback needs a genre for every deck game.

### Steam profile import

Later: an optional "skip the grid" accelerator. Playtime is strong behavioural
evidence, but owned is not loved, and a public profile adds friction.

## 4. Active hypothesis testing — the core loop

Adaptive testing / Bayesian experimental design over champion candidates.
Deterministic at runtime, no LLM in the loop. An LLM may draft the question
bank offline; a person approves it.

1. Answers so far -> a point and a shortlist of candidate champions around it
   (`scoring.neighbourhood`).
2. Compute what separates the top candidates: the direction between them in
   sub-trait space.
3. Ask the question that best splits that direction, chosen only from questions
   the user can surely answer: recognised games, deep dives of loved games,
   reasons for disliked games.
4. **Validator:** when one candidate leads, predict how a genuine fit would
   answer an unseen question, then ask it. Match -> confidence up, stop.
   Mismatch -> reopen.
5. Stop when the leader holds and predictions confirm.

### The unified question interface (the key design rule)

Every question of every type — versus, picker, verdict, genre, deep dive, why —
declares how each answer moves the estimate: which dimension or sub-trait, which
sign, what size, and how much it counts toward that dimension being read. That
makes types comparable, so the loop picks the best next question regardless of
type, and the mix varies between players as a consequence rather than by rule.

A declared effect may be *zero* — "not about the gameplay", "never really
played it" — and that is the most important effect the interface enables:
today no answer can remove evidence.

### What to generalise (both exist and do what the brainstorm says)

- `quiz.sensitivity()` — per dimension, how many of the top n champions a nudge
  of `NUDGE` displaces. Generalise "dimension" to "direction between the top
  candidates".
- `quiz.pair_for()` / `quiz.contrastive()` — a pair that splits one dimension by
  >= 0.35 while matching within 0.15 on the other two. Generalise to "a question
  whose declared effect projects onto that direction".
- `quiz.apply_comparisons()` caps cumulative movement at `scoring.CLOSE`
  because it runs after the result is shown; its docstring already says the cap
  comes off if questions move before the result. The loop moves them before.

### The noise floor — corrected number

The brainstorm put label noise at ~0.05. `quiz.py`'s 0.051 is something else:
the median distance from a champion to its **nearest neighbour** (the
justification for `NUDGE`). Measured label test-retest noise is 0.02-0.03 per
dimension at the aggregate level (max ~0.08), and 0.024-0.050 per sub-trait
(table in §2). Two candidates closer than that cannot be split by any question.
The honest output there is "either — here is the difference", not another
question.

## 5. Bias

A "love" is MMM signal plus nuisance: childhood, family, friends, art, story,
"it was what the PC could run". No champion can deliver most of that nuisance,
so for matching it is noise. Defences, stacked:

- **Bias-proneness prior per game** — "can you love this without engaging its
  demand?" Low: osu!, Factorio, Dark Souls, Tekken, rated chess. High: Durak,
  UNO, Monopoly, Minecraft, Mario Kart, family and childhood games.
  High-proneness loves count as weak evidence until a why confirms gameplay.
  Chess is per mode and context: with grandpa ~ Durak, rated online ~ osu! —
  which the deep tier already separates (`chess-blitz`, `chess-bullet`).
  *Data limit:* the Steam dataset carries average and median playtime only, no
  distribution, so "bimodal playtime" cannot be derived; the average-to-median
  ratio is the available skew proxy. Classic and family games are tagged by
  hand.
- **Why-for-loves, one tap:** the gameplay / the people I played with / the
  world or story / nostalgia / it was what I had. Only "the gameplay" carries
  MMM weight.
- **Triangulation:** trust patterns across games, not single games. A love
  inconsistent with the rest of a player's picks is down-weighted (a robust
  estimate, not the current opportunity-weighted mean in `quiz.estimate`).
- **Deep dives** are the most bias-resistant evidence: nostalgia explains
  loving CS, not choosing the AWP over a rifle.
- **The validator** catches residual bias.

**Transferable bias** (theme or fantasy: "I love guns", "dark fantasy") *can*
be delivered by a champion, but it is outside MMM. It may act only as a
tie-breaker among champions MMM already places close, and in explanation text.
Never in matching.

## 6. Output

**Decided 2026-09-28** (CLAUDE.md, replacing *Style first, role second*):

- **The product picks the lane.** Labels are champion x role, so the answer is
  a champion x role; a newcomer is not asked to choose a lane. The lane gets a
  light mention -- a wrong lane costs little, a wrong champion is the failure.
  Mechanically this is automatic and already true: `scoring.neighbourhood`
  keeps one entry per champion, with the role of that champion's nearest
  champion x role row. Nothing predicts a lane from the point -- which Gate 1
  measured as weak (top lane below chance) -- so none of that weakness applies.
- **The result reads the player** in plain language (§6.1) and never shows a
  champion's own sub-trait profile.
- **Each champion is presented minimally:** "Azir / mid" plus the one or two
  sub-traits that explain *this* match for *this* player. Two players matched to
  Azir get different reasons, because they reach him through different parts of
  his profile. `quiz.explain` already does this at dimension level (the trait
  the player is most decided about *and* the champion shares, or nothing); it
  generalises to the two contrasts.
- **The recommendation may be an ordered path** (start -> destination).
  Difficulty and Blue Essence price order the steps; neither is shown, and
  neither places the player -- which keeps *Three dimensions only* intact
  (difficulty is never a matching dimension or a UI concept).

### 6.1 The reading

"From your answers you seem like..." -- the appeal of a horoscope, which is
the point: people like being described. Two constraints keep it honest:

- **Only MMM, in player language.** Every phrase maps to a dimension or a
  contrast that was read. "High mechanics", "you set up plays before they
  happen", "you like knowing where to be" pass. "You love fast killing" does
  not -- that is tempo, a labelling input CLAUDE.md bars from the UI -- and
  neither does anything about teams unless a sub-trait carries it.
- **Unread is said, not filled.** A part of the reading the answers could not
  support is stated as open, with the retry offer (*reported, never imputed*).
  A horoscope invents; this one only describes what it measured.
- **Every phrase could be false for another player.** Horoscopes feel accurate
  to almost everyone (the Barnum effect), so a phrase that fits everyone
  describes no one. "You set up plays before they happen" is falsifiable -- a
  player at the other end of the meso split would reject it. "You're
  competitive but thoughtful" is Barnum and never ships. Each sentence in the
  bank is written as one side of a contrast, with its opposite beside it, so a
  reviewer can check that the opposite is a real player too.

**The reading must not contaminate the measurement.** A flattering, personal
reading gets rated "feels right" whether or not the champions fit. So the
"feels right?" question (§8) is asked about the *champions*, and asked
*before* the reading is shown.

Phrasing is a bank of approved sentences per dimension and contrast level,
drafted offline (an LLM may draft, a person approves) and assembled
deterministically at runtime -- no LLM in the loop.

### 6.2 Paths

Path cost = distance to the point + difficulty penalty + Blue Essence cost.

- Step 1: accessible, lower difficulty, cheap BE tier, a lane the player learns
  from. Later steps: closer to the point, harder, pricier, spaced by BE earn
  rate. No free-rotation integration.
- **Difficulty:** Data Dragon `info.difficulty`, in `champion_patch.raw` for
  all 173 champions, 0-10. **0 means missing, not easy**: Akshan, Rell,
  Seraphine and Vex are 0, and read naively Seraphine becomes the most
  accessible champion in the game. Also, the brainstorm's example "Ekko -> Azir"
  starts at 8/10 (Azir 9/10), so it does not satisfy its own step-1 rule.
- **Blue Essence price:** confirmed absent from Data Dragon (`raw` has no price
  field). Source from Community Dragon or the wiki; verify current tier prices
  and new-account earn rates at build time.
- **Sourced path structure:** `docs/champion-classes.md` names a purist and a
  recommended per class ("Zoe / Viktor", "Akali / Ekko", "Qiyana / Naafiri",
  "Vi / Nocturne", "Karma / Nami" — purist first), and defines recommended as
  "teaches the same skills but actually gets results": a first step by
  definition. Use as a prior or validation for paths. That file's "How to use
  it" names anchors only, so this is a new use; it does not touch the CLAUDE.md
  ban, which is on class tags as *labelling* input. Surnex's "attention in
  depth" (describe -> explain -> predict -> estimate -> delegate, noted in
  `docs/3m-model.md` as "possibly relevant later for a grow-into progression")
  is a second grounding from inside the model.
- **Support:** a penalty, not a ban; rare as a first step. Early only as (a) a
  support champion played in another lane the match data shows live, or (b) a
  low-difficulty enchanter or linear engager when clearly the best match.
  *Carve-out (a) matches nobody the brainstorm named:* Karma (support 90%),
  Seraphine (bot 19%) and Morgana (mid 25%) have no live row outside support at
  the 30% threshold. The supports that do are Lux (mid), Brand (bot) and Zyra
  (jungle).

## 7. What this means for the deck

Recognisability and spread first; deep-tier entries for the ~20 most-recognised
families second (the bank has 9 families today: chess, poker, durak, minecraft,
tetris, pokemon, league, roblox, garrys-mod); a bias-proneness value per game;
a genre for every deck game (§3); and search aliases — the names people type
("CS", "GTA", "LoL"), for which no field exists yet.

## 8. Measurement — panel round 2

- **The comparison pass** (`r3m panel-check`, `r3m.panel`; built 2026-09-28)
  places each player's recent mains in the space and reports three measures,
  in this order:
  1. **Personal fit** -- does *your* quiz point sit nearer your mains than
     other players' quiz points do? Other players are the baseline; by chance
     your own is closest 1 time in n. This is the question the panel exists for.
  2. **Distance to each main** (games-weighted) and **where your mains rank**
     from the quiz point (50% = chance).
  3. **Know-nothing**, the roster centre, as a reference only -- the point
     nearest on average to any champion, so a high bar, not a null.

  The first version measured against the *centroid* of a player's mains, and
  that was wrong: averaging five or more champions lands near the middle,
  where the know-nothing point sits, so it won by construction. Found on the
  first run, which is what a sanity check is for.

  It runs by hand on a development key fetched for the occasion (they expire
  every 24 hours). Fetched mains are cached in `data/panel-mains.json` and, with
  `--write`, stored on the session (`015_panel_mains.sql`), so re-analysis costs
  no Riot calls. `--write` needs migration 015 on the target database, and on
  production that cannot run before the merge: `r3m migrate` applies every
  pending migration, 012 included, which drops the `riot_region` column the
  code deployed from `main` still writes.

  **First run, 2026-09-28, n=3 -- a sanity check, not a result.** Personal fit
  1, 1 and 3 of 3; mains ranked 42%, 63% and 46% from the quiz point; the
  know-nothing reference nearer in all three. #15 (four loved games, point
  0.85/0.70/0.76) is the love-everything artefact slice 1 targets; #8 was read
  low on meso (0.40) while playing Hwei, Aurora and Azir -- the same misread
  quiz-flow.md once recorded by hand. Watch both in round 2. And what someone
  plays is habit and popularity as well as fit, so this measures fit only in
  part; the "do these champions feel right?" rating sits beside it.
- A "do these champions feel right?" rating: the product goal is
  satisfaction, and this tests whether the bias worries are overblown. Asked
  about the champions and before the reading appears (§6.1), or the Barnum
  effect measures the horoscope instead of the match.
- **Sample size.** Round 1 left three Riot ids, and two lack a tag line. That
  is a sanity check for the comparison pass, never a ranking of matcher
  variants -- with n=3 any difference is noise, and choosing on it fits the
  model to three friends. Round 2 makes the Riot id prominent and requires the
  #tag, and variant comparisons are reported as verdicts only past a minimum n
  (`r3m.panel`).
- The share of loves and dislikes given non-gameplay reasons: how much of
  today's signal is noise.
- Whether fill and retry games were answerable.

## 9. Decisions

Settled 2026-09-28: the two cancelling dislike reasons ("never really played
it", "not about the gameplay") ship in the first slice, since they only remove
noise; never-played via "the rest I haven't played" (§3);
"fine" at zero weight, recognised but not read (§3); the product picks the lane
(§6); the result reads the player and shows no champion sub-trait profile
(§6.1); the sub-traits in matching (§2); the comparison pass runs on a manually
fetched Riot development key (§8).

Still open:

1. **Macro weighting** toward routing (§2): a recommendation waiting on the
   CLAUDE.md open question about weights.
2. **When to spend on labelling** the 276 new deck games and 26 deep entries:
   a gate for adaptive rounds and deep dives, not for the first slice.
3. **Where bias-proneness lives** (bank files -> a `game` column) and who tags
   the first 50.
