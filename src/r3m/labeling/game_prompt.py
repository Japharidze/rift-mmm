"""Versioned system prompt for game labelling.

Same ten sub-traits and the same tool schema as champions — the dimensions do
not change because the subject does. What changes is the subject description
and the framing of the cheat test, which is about a *game* in Surnex's original
formulation and was rephrased for champions.

The model is given the title and, where it matters, the mode. Nothing else.
Champions had kit_text from Data Dragon; games have no such source, so this
leans on the model's own knowledge of the title. That is the cheaper option and
it makes the anchor pilot a real test of whether it suffices — but it is less
reproducible than kit_text, since a future model may know a game differently.
No category or genre hint is passed: handing over "pure macro" would give away
the answer the anchors exist to check.
"""

GAME_PROMPT_VERSION = "games-v1"

GAME_SYSTEM_PROMPT = """\
You score one game on the micro / meso / macro model (Surnex's framework --
this is an implementation of it, not an extension).

- micro: the execution layer. Aim, timing, movement, muscle memory.
- meso: the probability and mind-games layer. Reacting to the unpredictable
  behaviour of people, not mechanics. Prediction, deception, reading habits.
- macro: the systems layer. Routing, resource management, win conditions.
  The mathematically correct way to win.

The sharpest diagnostic for each: what cheat would make this game trivially
easy? A micro cheat is perfect inputs -- an aimbot. A meso cheat is knowing
something you should not: the opponent's hidden state, their intent, their
next move. A macro cheat is a perfect coach or engine telling you the
correct move.

Score ten sub-traits, each 0-1:

Micro
1. precision: how much does the game require precise aim, placement or
   timing of inputs?
2. execution: how much does it require chaining inputs in tight windows?
3. cheat: would perfect inputs alone make this game dramatically easier?

Meso
1. deception: how much does the game let a player disguise intent or
   threaten falsely?
2. prediction: how much does good play mean predicting something not yet
   shown, rather than reacting to something visible?
3. exploitation: how much does power come from reading this particular
   opponent's habits over time, rather than executing one fixed optimal line?
4. cheat: would knowing the opponent's hidden state before it happens make
   this game dramatically easier, independent of mechanical skill?

Macro
1. routing: how much of good play is about where to spend time and
   resources, rather than about the moment-to-moment action?
2. win_condition: how much does good play mean building toward a specific
   plan rather than winning exchanges in isolation?
3. cheat: would a perfect coach or engine -- telling you exactly what to
   prioritise, with no mechanical or read improvement -- make this game
   dramatically easier?

Rules:
- Scores are absolute and independent per dimension. They do not and must
  not sum to 1. A game can be low on all ten, high on all ten, or any mix.
  Solitaire is low on all three; Counter-Strike is high on all three.
- Score the game as it is commonly played. Where a mode is given, score that
  mode specifically.
- A single-player game can still be high on meso if it asks you to predict a
  system's hidden state -- but score that lower than reading a human, which
  is what meso is really about.
- Judge the game itself, not its reputation for being hard. Difficulty is
  not a dimension here; a game can be punishing and still low on all three.
- Respond only by calling the emit_champion_label tool. Do not add
  commentary outside it.
"""


def build_game_message(*, name: str, mode: str | None = None) -> str:
    return f"Game: {name}" + (f"\nMode: {mode}" if mode else "")
