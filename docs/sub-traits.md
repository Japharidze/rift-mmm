# Sub-traits — frozen

**Prompt v8** (2026-09-24) — v4, v5 and v6 were tried and rejected on
`macro_routing`; see history. v7 tried `micro_precision`/`micro_execution` and
`macro_win_condition`; the micro change was reverted after its control
(Kog'Maw) moved more than the motivating case, the win_condition change was
kept. v8 is that combination: v3's micro wording, v7's win_condition wording,
`macro_routing` still untouched. Version history is at the end of this file.

Ten sub-traits feed the three MMM aggregates: 3 micro, 4 meso, 3 macro (the
allocation and its rationale are in `CLAUDE.md`, Frozen decisions). Frozen
2026-09-22. Do not edit mid-run — a re-labelling run against changed wording
is a new prompt version, not a fix.

Each is written to be judgeable from a champion's kit text + role, not from
vibes about the champion's identity, and without reaching for Riot's class
tags (see `CLAUDE.md`, Attribution). The last sub-trait in each group is the
cheat test from `docs/3m-model.md`, rephrased from "what cheat breaks this
game" to "what cheat breaks this champion."

## Micro

1. **Precision demand** — how much do the core abilities require landing
   skillshots or precise placement, vs. auto-target or self-cast? (Reverted to
   v3's wording at v8 — see version history, v7.)
2. **Execution/combo demand** — how much does effective use require chaining
   abilities in a tight timing window (cancels, resets, combo order)?
   (Reverted to v3's wording at v8 — see version history, v7.)
3. **Cheat test** — would perfect inputs (every skillshot lands, every combo
   flawless, zero misclicks) alone make this champion dramatically stronger?

## Meso

1. **Deception potential** — how much does the kit let the champion disguise
   intent or threaten falsely (fake-casts, stealth, an engage that reads as a
   disengage)?
2. **Prediction under hidden information** — how much does the kit force
   commitment before the enemy has shown what they will do? Instant,
   point-and-click, or mid-flight-steerable abilities need little prediction:
   the enemy acts and you respond. Slow projectiles, long cast times,
   ground-targeted zones and pre-placed traps must be aimed where the enemy
   *will* be, and score high. Judge the abilities, not the fact that League
   rewards prediction in general.
3. **Opponent-specific exploitation** — how much does power come from reading
   *this* opponent's habits over a match, rather than executing one fixed
   optimal line?
4. **Cheat test** — would knowing the enemy's hidden state (cooldowns,
   position, next input) before it happens make *this* champion dramatically
   stronger than it would make an average champion? Every champion gains
   something from it; score high only where the kit turns that knowledge into
   something other champions could not do with it.

## Macro

1. **Map agency** — how many decisions about *where to be* does this
   champion's player actually make, and how much do those decisions change the
   game? A champion locked to one lane, who moves when the team moves, scores
   low even though the map still matters — those decisions are being made for
   them. A champion who chooses between objectives, decides when to abandon a
   lane, or whose presence somewhere else constrains what the enemy can do,
   scores high.
2. **Win-condition construction** — how much does good play mean actively
   deciding *when and how* to pursue a late-game plan, rather than converging
   on one because it exists? A stacking or scaling mechanic is not enough by
   itself: if the target and timing are the same regardless of what the enemy
   does — farm safely, hit the number, you are strong — that is a fixed
   progression, not a decision. Score high only where the plan's timing or
   shape branches on the game state: contesting objectives around it,
   choosing when to force a fight versus scale further, or reacting to what
   the enemy is doing to reach it.
3. **Cheat test** — would a perfect coach — telling you exactly where to be
   and what to prioritize, no mechanical or read improvement — make *this*
   champion dramatically stronger than the same coaching would make an average
   champion? Advice that would help any player equally is not this champion's
   macro.

## Why this wording, not something else

Reasoned by hand against five anchors from `anchors/champions.yaml`, chosen to
stress different edges of the scale rather than just the flat high/low cases:

- **LeeSin** (0.90/0.80/0.82, the ceiling anchor): insec-kick combos and Q1
  targeting push all three micro sub-traits high; jungle pathing/invades push
  meso's prediction and opponent-read sub-traits high; the jungle role itself
  maxes the routing sub-trait. All three land high, as anchored.
- **Garen** (0.12/0.18/0.38): no skillshots and minimal combo floor out
  micro; no bluff or read surface floors out meso. Macro lands *higher* than
  either, because win-condition construction (scale + split-push) and routing
  value pick up real signal even from a mechanically simple kit — matching
  the anchor's low-mid-vs-low split rather than flattening him to floor on
  everything.
- **Riven** (0.87 / 0.50 provisional / 0.40): the anchor file's own note says
  meso was moved down because perfect execution trivialises Riven far more
  than knowing enemy intent does. Scoring the micro and meso cheat tests
  separately reproduces that directly — the micro cheat test is a dramatic
  power spike, the meso one a real but smaller one.
- **TwistedFate** (0.52/0.72/0.90): W's card guess is a meso mechanic built
  into the kit; R is a global teleport, so routing value and the macro cheat
  test both max out. Matches closely, including macro landing highest of any
  anchor.
- **Yuumi** (0.35/0.20/0.20, the macro floor, with a note that micro isn't
  floor because Q is manually aimed): precision demand is scoped to whether
  the kit has an aimed component at all, so it picks up Q without inflating
  from the rest of the passive kit — matching the anchor's explicit exception
  instead of flattening her to zero on everything.

No misfires, including the two anchors hand-annotated as exceptions (Riven's
meso, Yuumi's micro) — the harder bar than matching the easy cases.


## Version history

### v7 — 2026-09-24

Anchor check on the canonical v3 set (runs 9+10, 196 rows, matched by role)
found 31/75 blocking failures on the 25 tight anchors — 9 micro, 9 meso, 13
macro — traced to stored rationale text, not generic noise:

- **`micro_precision`/`micro_execution` are ability-cast-specific**
  ("vs. auto-target or self-cast" frames autoattacking as inherently low
  precision), so champions whose test is auto-attack positioning and kiting
  rather than ability skillshots score low regardless of how demanding that
  positioning actually is. Ashe is the clean case: micro 0.43 against an
  anchor band of 0.65–0.88, because her rationale scored the ability kit
  ("mechanical load is modest") and never asked about auto-attack spacing.
- **`macro_win_condition` credits any scaling mechanic as a "plan"**, with no
  test for whether the plan is a genuine decision or a fixed target every
  player converges on the same way. Smolder (0.64 against 0.10–0.32) and
  Teemo (0.68 against 0.10–0.32) are both rationalised as "building toward a
  specific spike" — true, but the spike's timing does not depend on what the
  enemy does, which is exactly what the sub-trait failed to ask.

`macro_routing` is not touched this round even though it produced the most
failures (13/25): three prior rewrites (v4, v5, v6, below) already failed on
this sub-trait specifically, changing it alongside two other sub-traits would
make any pass-rate movement unattributable to any one of the three, and
`macro_win_condition` is adjacent to it (Teemo's routing rationale — "shroom
placement... constrains enemy routing" — may partly be win_condition's
scaling-credit bug leaking into routing's score). Routing gets re-measured
after this run, not rewritten blind.

**Prediction, registered before running** (label_run TBD, 25 anchors +
Kog'Maw + Kassadin as controls):

| champion | before (micro/meso/macro) | expected | why |
| --- | --- | --- | --- |
| Ashe (anchor) | 0.43 / 0.59 / — | micro up toward 0.65–0.88, meso down toward 0.10–0.32 | the motivating case |
| Kog'Maw (control) | 0.56 / — / — | little to no change | near-zero mobility — a fix that lifts him anyway is pattern-matching on auto-attack damage, not reading the kit |
| Smolder (anchor) | — / — / 0.64 | down toward 0.10–0.32 | the motivating case |
| Teemo (anchor) | — / — / 0.68 | down toward 0.10–0.32, but possibly not all the way if routing's own credit is doing some of the work | motivating case, adjacent-dimension leakage |
| Kassadin (control) | — / — / 0.77 | little to no change | late-game plan genuinely branches on lane state and enemy position — a real decision, not a fixed breakpoint |

**Stopping rule, committed before the run:** win_condition and micro count as
fixed only if Kog'Maw and Kassadin do not move materially alongside the
motivating cases. A version that raises Ashe's micro but also raises Kog'Maw's,
or lowers Smolder's macro but also lowers Kassadin's, has pattern-matched on
class rather than read the kit, and is reverted like v4–v6.

**Result, measured against all 25 anchors + both controls (label_run 18):**

| champion | dim | v3 | v7 | delta |
| --- | --- | --- | --- | --- |
| Ashe (motivating) | micro | 0.43 | 0.54 | +0.11, still fails (band 0.65–0.88) |
| Ashe (motivating) | meso | 0.59 | 0.59 | unchanged — meso wasn't in scope this round; the prediction table above should not have listed this as an expected move, that was an error in the prediction, not the fix |
| **Kog'Maw (control)** | micro | 0.56 | **0.82** | **+0.26 — larger than Ashe's own move** |
| Smolder (motivating) | macro | 0.64 | 0.57 | -0.07, still fails (band 0.10–0.32) |
| Teemo (motivating) | macro | 0.68 | 0.66 | -0.02, barely moved |
| Kassadin (control) | macro | 0.77 | 0.76 | -0.01, held |

Overall: 30/75 blocking failures against v3's 31/75 (micro 10/25, meso 9/25,
macro 11/25) — statistically flat, not the clean improvement hoped for.
Orianna and Camille (real ability-combo kits, not auto-attack-centric) also
drifted further over their micro bands under the new wording (+0.03 and
+0.05), a second sign the precision rewrite was reading as a general "raise
micro" signal rather than a kit-specific one.

**Verdict, applying the stopping rule as committed:**

- **`micro_precision`/`micro_execution`: reverted.** Kog'Maw moved more than
  the motivating case despite an explicit instruction not to score high "just
  because a champion deals damage through auto attacks" — his own rationale
  argued the *absence* of mobility tools makes spacing *harder*, which the
  wording did not anticipate or block. Textbook pattern-match, exactly what
  the control was built to catch.
- **`macro_win_condition`: kept.** Kassadin held flat, so it passes its own
  stopping test even though it did not fully fix Smolder or Teemo. Teemo
  barely moving at all (-0.02) is itself informative: it says his over-score
  is coming mostly from `macro_routing` (untouched this round), not
  `win_condition` — consistent with the reasoning for leaving routing alone
  and re-measuring it before rewriting it.

Net effect: the live prompt is neither v3 nor v7, but a new combination —
v3's micro wording restored, v7's win_condition wording kept, routing still
untouched. That is **v8**, below.

### v8 — 2026-09-24

Carries forward from v7: `macro_win_condition` kept as written there (see the
v7 result above), `micro_precision`/`micro_execution` reverted to v3's wording
after the Kog'Maw control caught it pattern-matching. `macro_routing` remains
untouched, now with two data points (v7's Teemo, this section's reasoning)
suggesting its own rewrite should target the "presence constrains the enemy"
clause specifically rather than routing wholesale.

Not yet re-measured against the full anchor set as its own combined version —
the pieces are each validated individually (win_condition against its
motivating cases + Kassadin; micro's revert is a return to the already-known
v3 numbers), but a full v8 pass has not been run.

### v4, v5 and v6 — tried and rejected, 2026-09-22

Three consecutive attempts to fix macro by rewording `macro_routing`. All three
are reverted; the wording below is v3's. They are recorded because the measured
result is the most useful thing anyone reconsidering this sub-trait can have.

Correlation with the 25 anchors, and bias, measured identically across versions:

| version | micro | meso | **macro** | macro bias |
| --- | --- | --- | --- | --- |
| **v3** | 0.83 | 0.71 | **0.53** | +0.08 |
| v5 | 0.82 | 0.68 | 0.44 | +0.10 |
| v6 | 0.84 | 0.70 | 0.46 | +0.15 |

**Every version after v3 made macro worse.** Each looked like progress while
being judged on the five champions under discussion — Blitzcrank, Yuumi,
Soraka, Thresh, Morgana — and each degraded ordering across the full anchor
set. That is the lesson worth keeping: judge a prompt change on the whole
anchor set, never on the cases that motivated it.

What each attempt was, and what it did:

- **v4** reframed map agency from location to decision ownership, after both
  Sergi's ranking and `docs/champion-classes.md` showed supports underrated.
  Null: Blitzcrank +0.05, support-specific shift ~+0.005 once global drift is
  removed, against the +0.20 the evidence called for.
- **v5** reframed again as *decision load* across four kinds — where to be,
  what to invest in, whom to commit to, when to commit. The first version to
  change the distribution's *shape* rather than shift it (support +0.07, top
  and jungle down). Enchanters moved most: Soraka +0.13, Milio +0.13. But
  Blitzcrank did not move and Yuumi's floor broke, 0.25 -> 0.48.
- **v6** scored decisions on consequence rather than on how many kinds they
  span, aiming at both defects with one edit. It fixed neither — Blitzcrank
  +0.03, Yuumi 0.48 -> 0.55 — and lost v5's redistribution, inflating every
  role instead.

A stopping rule was committed before v6 ran: if it did not both raise
Blitzcrank and return Yuumi to the floor, wording was done on this dimension.
It did neither. The remaining correction is calibration against anchors, not
prompting.

Note also that macro's 0.53 at v3 is flattered: two of the 25 anchors, Azir and
Orianna, had their macro conceded to the labeller. Across the 12 never-conceded
anchors, v3's macro correlation was 0.13.

### v6 — 2026-09-22

v5 was the first version to change the *shape* of the macro distribution rather
than shift it: support +0.07 and bot +0.05 while top and jungle fell, with the
overall mean moving only +0.02. The enchanters moved most — Soraka +0.13, Milio
+0.13, Morgana +0.10 — which is the "whom to commit to" kind landing, and the
reason to keep this framing.

Two defects, and both trace to one word: **"score high where the kit forces
*several* of these"** made the score count decision *kinds* rather than decision
*stakes*.

- **Blitzcrank did not move** (0.33 -> 0.32). He forces essentially one kind,
  when to commit, but forces it constantly and losing that decision loses the
  game. A variety-counting rule scores that low.
- **Yuumi's floor broke** (0.25 -> 0.48). She nominally touches "whom to commit
  to", so she was credited for a choice whose answer is always the carry.

Rewritten to score on consequence, with an explicit statement that one decision
repeated can score as high as four kinds, and that a nominal choice with a
fixed answer scores low regardless of frequency.

**Stopping rule, committed before the run:** if v6 does not both raise
Blitzcrank and return Yuumi to the floor, wording has done what it can on this
dimension and the remaining correction is calibration, not prompting.

### v5 — 2026-09-22

v4 was a null: Blitzcrank's macro moved 0.33 -> 0.38 and Thresh's 0.42 -> 0.49,
both under the 0.08 noise ceiling, and the support-specific shift was about
+0.005 once the global drift is removed — against the +0.20 the evidence called
for.

The cause was not the input, as first supposed. Every version of this sub-trait
since v2 asked about **location** — "map agency", "where to be", and even v4's
correction stayed inside the frame ("who decides when to leave it"). But macro
is the systems layer, and relocation is one decision type among several. A
jungler decides *what to invest in*; Soraka decides *whom to peel*; Blitzcrank
decides *when to commit*. Supports and top bruisers — the two groups the
labeller underrated — make their decisions almost entirely in those last two
kinds, so a question about location scored them as passengers.

The information was in the kit text all along. Soraka's text says she heals an
ally; Blitzcrank's says he pulls an enemy on a long cooldown. We were asking
about the wrong fifth of the construct.

Reframed from location to decision load, with the kinds named and declared
equal. The stored column stays `macro_routing` — renaming it would cost a
migration and buy nothing.

### v4 — 2026-09-22

v2's `macro_routing` fixed one flaw and introduced another. "A champion locked
to one lane, who moves when the team moves, scores low" reads a support as a
passenger, and the labeller took it literally: support has the lowest mean
macro of any role (0.45, against jungle's 0.69), and Blitzcrank — whom coaches
place in the highest-ceiling, most cerebral group in the game — came back at
0.33.

Two independent sources say that is wrong, which is why it is worth a version:

- Sergi's own anchor ranking put Milio 3rd on macro where the labeller put it
  10th, Morgana 6th against 12th, Lux 7th against 11th. Three of the four
  largest disagreements were supports.
- `docs/champion-classes.md`, distilled from coaching content that owes nothing
  to this project, describes playmaker supports as needing wincon assessment,
  tempo, fog and man advantage — macro by every definition in this file.

So the low anchor is rewritten from *location* to *decision ownership*, vision
and fight-timing are named as routes to agency, and the "has a lane, therefore
low" inference is blocked outright. Nothing else changes, so a v3 -> v4
difference is attributable to this sub-trait.

### v3 — 2026-09-22

v2's macro rewrite worked and its global range instruction did not, which
settled how to fix a dimension: reword the specific sub-trait, do not tell the
model to use more of the scale. Measured v1 -> v2 over the 13 anchors, macro
correlation went 0.58 -> 0.77 and its error on low-anchored champions nearly
halved, while micro was unchanged and meso compressed *further* (spread 0.69x
-> 0.63x). So meso now gets the treatment macro got, and nothing else changes:

- **`meso_prediction`** asked whether good play means predicting the enemy.
  True of every champion in a PvP game, so it measured the game, not the kit --
  the same flaw `macro_routing` had. Now asks whether the *kit* forces
  commitment before the enemy reveals, with instant and point-and-click
  abilities named as the low end.
- **`meso_cheat`** asked whether knowing hidden state would help. It helps
  everyone. Now relative to an average champion, matching what `macro_cheat`
  became in v2.

`meso_deception` and `meso_exploitation` are untouched, as is everything in
micro and macro, so a v2 -> v3 difference is attributable to these two.

### v2 — 2026-09-22

Measured against the 13 anchor champions under v1 (label_run 2), plus a
test-retest pair (runs 1 and 3, same prompt, same model):

- **macro never went below 0.37** while anchors run down to 0.20, and macro
  correlated with the anchors at only 0.58 — the weakest of the three.
  `macro_routing` was also the joint-noisiest sub-trait across the retest
  (mean |diff| 0.043). Both point at the same wording: "where they spend time
  on the map" is true of every champion, so it was being answered as *does
  this game have macro* rather than *does this champion demand macro*.
  Rewritten as **map agency** — decisions made, not location occupied.
- **`macro_cheat`** let any champion score mid, since a coach helps anyone.
  Now asks for the effect *relative to* an average champion.
- **All three dimensions compressed** toward the middle (spread 0.66-0.69x of
  the anchors' for meso and macro; lows pulled up, highs pulled down). Added
  an explicit range instruction with endpoint anchors, which applies to all
  ten sub-traits, not just macro.

This bundles two interventions — the macro rewrite and the global range
instruction. If micro shifts, it will not be attributable to one of them.
Deliberate: both were diagnosed, and a third run to separate them costs more
than the attribution is worth at pilot scale.

### v1 — 2026-09-22

First wording. Text recoverable from git history at
`src/r3m/labeling/prompt.py`.
