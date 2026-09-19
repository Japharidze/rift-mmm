# The micro / meso / macro model

Source: Surnex, two videos.
1. "Once you see this, You'll see Competitive Games Differently" — https://youtu.be/NgHvdCcmQ4o
2. Follow-up, on MMM as a model of attention rather than of games.

Raw transcripts in `docs/transcripts/`.

## The core claim

Every competitive game separates good players from bad through three different
kinds of demand:

- **Micro** — the execution layer. Aim, timing, movement, muscle memory.
- **Meso** — the probability and mind-games layer. Reacting to the unpredictable
  behaviour of people, not mechanics. Prediction, deception, reading habits.
- **Macro** — the systems layer. Routing, resource management, win conditions.
  The mathematically correct way to win.

Genre labels don't tell you which of these a game demands. These three do.

## The cheat test

The sharpest diagnostic: **what cheat would make this game trivially easy?**

- Micro cheat = aimbot, perfect inputs. Breaks osu!, Geometry Dash, aim trainers,
  Tetris.
- Meso cheat = stream sniping, insider information, seeing cooldowns or intent —
  knowing something you shouldn't, not executing better. Breaks Among Us,
  Liar's Bar, and (his aside) the stock market.
- Macro cheat = a chess engine, economy automation, a perfect coach telling you
  the right move. Breaks Factorio, Poly Bridge, Connect 4, tic-tac-toe.

Note meso is the cheat-resistant layer in practice: the hidden information lives
in the opponent's head, not in the game state.

## Placements he states

Use these as calibration anchors when fitting sub-trait weights on the game side.

- **Pure micro:** osu!, Geometry Dash, Tetris, aim trainers
- **Pure meso:** rock-paper-scissors (his purest example), Among Us, Liar's Bar
- **Pure macro:** Factorio, Poly Bridge, Connect 4, tic-tac-toe
- **Micro + macro** (single-player precision): Rubik's cube speedrunning,
  Mario 64, Jump King, Getting Over It, Elden Ring. Outlier: 8-ball pool — PvP
  but almost no room for mind games.
- **Micro + meso** (PvP skill expression): Street Fighter, Tekken, Smash,
  Brawlhalla, Mario Kart, Fall Guys, Gang Beasts, Tetris 99 (original Tetris is
  pure micro; 99 adds meso through garbage targeting).
- **Meso + macro** (mind and math): Hearthstone, TFT, Pokémon VGC, Battleship,
  Balatro, Phasmophobia. Chess is theoretically pure macro but meso-heavy at the
  human level, since you optimise against a specific opponent's habits. He
  suspects non-PvP meso+macro games drift toward pure macro as players map the
  RNG.
- **All three:** League, Dota 2, CS2, Valorant, Overwatch, Marvel Rivals, Rocket
  League, Apex, Rainbow Six, WoW — but with different balances:
  - **CS2** — micro extremely high (aimbot alone nearly wins), meso high
    (wallhack experiments: one X-ray player usually loses to five, but steals
    rounds), macro relatively lowest.
  - **Rocket League** — micro dominant (mechanics beat smarts; AI bots beat
    semi-pros), then macro, meso last, since all information is knowable anyway.
  - **Apex** — remarkably balanced; aimbot, wallhacks, or perfect ring knowledge
    each give a real chance.
  - **Overwatch** — varies by role: DPS micro, tank meso, support macro. Framed
    as offence / control / defence respectively.

## The second video: MMM as attention, not as games

The more useful claim for this project. MMM describes how a player uses
attention, so it describes the *person*, not just the game.

**Attention in time.** Each layer prepares and resolves at a different distance
from the event:

| Layer | Before the event | After the event |
| --- | --- | --- |
| Micro | anticipate | react |
| Meso | suspect | recognise |
| Macro | strategise | calculate |

**Time pressure moves a game between layers.** Compress the time available and a
macro game behaves like a micro game (expert Minesweeper becomes
anticipate–react). Stretch the time out and remove the pressure and a micro game
stops being micro (slowed osu! with a remembered click order becomes a memory
game). So the layer is not a fixed property of the game — it depends on the time
available.

**Labelling rule that follows:** score a game as commonly played. Where a format
genuinely changes the answer, treat formats as separate rows (chess-blitz and
chess-classical are two items). Same rule as champion×role on the other side.

**Attention in depth** (the second dimension, about expertise rather than
taste): describe → explain → predict → estimate → delegate. Sequential — you
can't explain without describing, can't estimate without experience. Not used
for matching here; possibly relevant later for a "grow into" progression.

## Why this project takes the second video as its premise

If MMM describes attention rather than game design, then a person's preferences
across games they already know should transfer to what they'll enjoy in League.
That transfer is the product's central bet — and the thing the MVP is built to
test, not to assume.

## Construct parallels

Not required, but supports that the three-way split isn't arbitrary:

- **Rasmussen's SRK** (human factors, 1983): skill-based / rule-based /
  knowledge-based behaviour — the closest structural match.
- **Level-k reasoning** (behavioural game theory): the recursive "I think that
  you think" ladder is meso, formalised.
- **Coaching's four pillars:** technical / tactical / psychological maps onto
  micro / macro / meso.
- **Levels of war:** tactical / operational / strategic — why the words feel
  natural, though it's the sociological sense rather than the cognitive one.
