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

**The game side cannot place a player on the meso split.** Game labels are
stable (games-v1 vs v2, run 15 vs 17, micro/meso wording unchanged: noise 0.03-0.07
of spread) but in games deception and prediction correlate **+0.89**: a game
that asks for mind-games asks for both. A player's point is built from the games
they pick, so picks alone cannot tell an anticipator from a concealer, however
fine the champion labels are. That resolution has to come from evidence that
*does* separate them: deep dives (§3 step 4) and why-answers (§5). The 276
unlabelled bank games may add contrast (stealth games, skillshot-heavy games);
measure once they are labelled, do not assume.

**Surnex's before/after axis** (`docs/3m-model.md`, attention in time:
anticipate/react, suspect/recognise, strategise/calculate) is a within-model
axis from the source itself, but no sub-trait is defined along it. Using it
means new labels, so it is out of scope until a prompt version adds it.

**Honest-output rule.** Precision is capped by label quality. The result says
where resolution is real (micro, meso-prediction vs concealment when deep-dive
evidence exists) and where it is not (macro, beyond its aggregate). An
unread sub-trait falls back to its dimension's aggregate and is reported as
such — the sub-trait version of "reported, never imputed".

## 3. The chain

1. **Recognition sweep.** Adaptive rounds of ~12 cards; each card is
   "played / never played" as a positive answer, never silence. Search box as a
   fallback. (See open decision 1 for how a positive answer stays fast.)
2. **Verdicts on recognised games only:** loved / fine / didn't like.
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

## 6. Output: a path, not a point — PENDING two conflicts

The point is the destination. The recommendation is an ordered path: start
champion -> one or two steps -> destination.

**Not frozen yet.** As written, this conflicts with two frozen decisions in
CLAUDE.md, and they have to be amended deliberately rather than overridden by
this doc (open decision 2):

- *Style first, role second* fixes the output as "MMM point -> style
  neighbourhood -> 3-5 champions labelled by lane -> user picks the lane". A
  path is a different output, and a path that crosses lanes (bot -> support)
  takes the lane choice away from the user.
- *Three dimensions only* lists difficulty among traits that are "never ...
  matching dimensions or UI concepts". A difficulty penalty in path cost
  arguably stays out of *matching* (it orders a path, it does not place
  anyone), but "start here, it is easier" in the result makes difficulty a UI
  concept.

Design, for when those are resolved. Path cost = distance to the point +
difficulty penalty + Blue Essence cost.

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

- Gap between the quiz point and the centroid of the player's mains. Schema
  exists (`011_panel.sql`: `actual_point`, `actual_games`, `checked_at`) and
  `db.py` has the read and write, but **the comparison pass itself is not
  built**: there is no caller, and `riot_api.py` has no account-v1 by-riot-id
  lookup.
- A "does this feel right?" rating: the product goal is satisfaction, and this
  tests whether the bias worries are overblown.
- The share of loves and dislikes given non-gameplay reasons: how much of
  today's signal is noise.
- Whether fill and retry games were answerable.

## 9. Open decisions

Listed with the staged plan in the session that wrote this doc; repeated here
so the doc stands alone.

1. How "never played" stays a positive answer without a tap per card.
2. The path conflicts (§6): amend *Style first, role second* and the
   difficulty-as-UI rule, or change the path design.
3. Whether sub-traits appear by name in the UI or only as plain-language
   explanation under their dimension (the Attribution section: this project's
   decomposition must not read as an extension of Surnex's model).
4. Which sub-traits enter matching (proposal: micro_precision,
   meso_deception, meso_prediction; not meso_exploitation, meso_cheat or any
   macro sub-trait) — and whether sub-trait matching waits until deep dives can
   supply within-meso evidence (§2, game side).
5. The weight of "fine", and whether it counts toward a dimension being read.
6. Where bias-proneness lives (bank files -> a `game` column) and who tags it.
7. When to spend on labelling the 276 new deck games and 26 deep entries
   (a gate for adaptive rounds and deep dives, not for the first slice).
