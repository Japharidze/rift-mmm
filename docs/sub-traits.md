# Sub-traits — frozen

**Prompt v3** (2026-09-22). Version history is at the end of this file.

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
   skillshots or precise placement, vs. auto-target or self-cast?
2. **Execution/combo demand** — how much does effective use require chaining
   abilities in a tight timing window (cancels, resets, combo order)?
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
2. **Win-condition construction** — how much does good play mean building
   toward a specific late-game plan (power spikes, objective timing) rather
   than winning exchanges in isolation?
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
