"""Versioned system prompt for champion labelling.

Never edit an existing version in place. Bump PROMPT_VERSION and every label
row records which version produced it (CLAUDE.md, Conventions) -- a run
against changed wording is a new prompt, not a fix to the old one.

The sub-trait wording quoted below is copied from docs/sub-traits.md, which is
the frozen source. If the two ever disagree, docs/sub-traits.md is correct and
this file is stale and needs a version bump.
"""

PROMPT_VERSION = "v1"

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
2. prediction: how much does effective use mean predicting something the
   enemy hasn't shown yet (flash timing, dash direction, whether a cooldown
   is up), rather than reacting to something visible?
3. exploitation: how much does power come from reading this specific
   opponent's habits over a match, rather than executing one fixed optimal
   line?
4. cheat: would knowing the enemy's hidden state before it happens make this
   champion dramatically stronger, independent of mechanical skill?

Macro
1. routing: how much of the champion's value comes from where they spend
   time on the map (roaming, split-push, jungle pathing, wave management)
   rather than from fights themselves?
2. win_condition: how much does good play mean building toward a specific
   late-game plan (power spikes, objective timing) rather than winning
   exchanges in isolation?
3. cheat: would a perfect coach -- telling you exactly where to be and what
   to prioritize, no mechanical or read improvement -- make this champion
   dramatically stronger?

Rules:
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
