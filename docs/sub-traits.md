# Sub-traits — frozen

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
2. **Prediction under hidden information** — how much does effective use mean
   predicting something the enemy hasn't shown yet (flash timing, dash
   direction, whether a cooldown is up), rather than reacting to something
   visible?
3. **Opponent-specific exploitation** — how much does power come from reading
   *this* opponent's habits over a match, rather than executing one fixed
   optimal line?
4. **Cheat test** — would knowing the enemy's hidden state (cooldowns,
   position, next input) before it happens make this champion dramatically
   stronger, independent of mechanical skill?

## Macro

1. **Routing/resource value** — how much of the champion's value comes from
   *where* they spend time on the map (roaming, split-push, jungle pathing,
   wave management) rather than from fights themselves?
2. **Win-condition construction** — how much does good play mean building
   toward a specific late-game plan (power spikes, objective timing) rather
   than winning exchanges in isolation?
3. **Cheat test** — would a perfect coach — telling you exactly where to be
   and what to prioritize, no mechanical or read improvement — make this
   champion dramatically stronger?

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
