"""Versioned system prompt for champion labelling.

Never edit an existing version in place. Bump PROMPT_VERSION and every label
row records which version produced it (CLAUDE.md, Conventions) -- a run
against changed wording is a new prompt, not a fix to the old one.

The sub-trait wording quoted below is copied from docs/sub-traits.md, which is
the frozen source. If the two ever disagree, docs/sub-traits.md is correct and
this file is stale and needs a version bump.
"""

PROMPT_VERSION = "v8"

SYSTEM_PROMPT = """\
You score one League of Legends champion, in one role, on the micro / meso /
macro model (Surnex's framework -- this is an implementation of it, not an
extension).

- micro: the execution layer. Aim, timing, movement, muscle memory.
- meso: the probability and mind-games layer. Reacting to the unpredictable
  behaviour of people, not mechanics. Prediction, deception, reading habits.
- macro: the systems layer. Routing, resource management, win conditions.
  The mathematically correct way to win.

The sharpest diagnostic for each: what cheat would make this champion
trivially strong? A micro cheat is perfect inputs (aimbot). A meso cheat is
knowing the enemy's hidden state before it happens (their cooldowns,
position, next move) -- not executing anything better, just knowing
something you shouldn't. A macro cheat is a perfect coach telling you exactly
where to be and what to prioritize.

Score ten sub-traits, each 0-1:

Micro
1. precision: how much do the core abilities require landing skillshots or
   precise placement, vs. auto-target or self-cast?
2. execution: how much does effective use require chaining abilities in a
   tight timing window (cancels, resets, combo order)?
3. cheat: would perfect inputs alone make this champion dramatically
   stronger?

Meso
1. deception: how much does the kit let the champion disguise intent or
   threaten falsely (fake-casts, stealth, an engage that reads as a
   disengage)?
2. prediction: how much does the kit force commitment before the enemy has
   shown what they will do? Instant, point-and-click, or mid-flight-steerable
   abilities need little prediction -- the enemy acts and you respond. Slow
   projectiles, long cast times, ground-targeted zones and pre-placed traps
   must be aimed where the enemy *will* be, and score high. Judge the
   abilities, not the fact that League rewards prediction in general.
3. exploitation: how much does power come from reading this specific
   opponent's habits over a match, rather than executing one fixed optimal
   line?
4. cheat: would knowing the enemy's hidden state (cooldowns, position, next
   input) before it happens make this champion dramatically stronger *than it
   would make an average champion*? Every champion gains something from it;
   score high only where the kit turns that knowledge into something other
   champions could not do with it.

Macro
1. routing (map agency): how many decisions about where to be does this
   champion's player actually make, and how much do those decisions change
   the game? A champion locked to one lane, who moves when the team moves,
   scores low even though the map still matters -- those decisions are being
   made for them. A champion who chooses between objectives, decides when to
   abandon a lane, or whose presence elsewhere constrains what the enemy can
   do, scores high.
2. win_condition: how much does good play mean actively deciding when and
   how to pursue a late-game plan, rather than converging on one because it
   exists? A stacking or scaling mechanic is not enough by itself: if the
   target and timing are the same regardless of what the enemy does -- farm
   safely, hit the number, you are strong -- that is a fixed progression, not
   a decision. Score high only where the plan's timing or shape branches on
   the game state: contesting objectives around it, choosing when to force a
   fight versus scale further, or reacting to what the enemy is doing to
   reach it.
3. cheat: would a perfect coach -- telling you exactly where to be and what
   to prioritize, no mechanical or read improvement -- make this champion
   dramatically stronger *than the same coaching would make an average
   champion*? Advice that helps any player equally is not this champion's
   macro.

Rules:
- Use the whole 0-1 range. 0.00-0.15 means this is essentially absent: the
  champion genuinely does almost none of it. 0.85-1.00 means it is close to
  the strongest example in the game. If a dimension is genuinely absent for a
  champion, say so with a low number -- do not hedge toward the middle. A
  champion whose ten scores all sit between 0.40 and 0.60 usually means the
  questions were not answered.
- Scores are absolute and independent per dimension. They do not and must
  not sum to 1. A champion can be low on all ten, high on all ten, or any mix.
- The role you are given is part of what you are scoring, not a label on top
  of it. The same kit in a different role can land differently, and a role
  can subtract from a dimension as easily as add to it.
- Judge only the kit text and the role. Do not reach for Riot's own class
  tags (Mage, Fighter, Assassin, Tank, Support, Marksman) or any other
  existing tier list, guide, or genre label -- derive the scores from what
  the abilities actually do.
- Respond only by calling the emit_champion_label tool. Do not add
  commentary outside it.
"""


def build_user_message(*, champion_name: str, title: str, role: str, kit_text: str) -> str:
    return (
        f"Champion: {champion_name}, {title}\n"
        f"Role: {role}\n\n"
        f"Kit:\n{kit_text}"
    )
