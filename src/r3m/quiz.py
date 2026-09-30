"""What a player enjoys -> an MMM point -> champions.

The concept is taste, not exposure. CLAUDE.md: "a player's *taste* in games
they already know points toward champions worth trying", and docs/3m-model.md
bets that *preferences* transfer because MMM describes the person. An earlier
version of this module asked "have you played X", which nearly everyone answers
yes to for Minecraft and which says nothing about whether they enjoyed it.

So an answer is three-way, and each one means something different:

  loved        positive evidence: you enjoy that level of demand
  didn't stick negative evidence: you met that level and it did not hold you
  never played no evidence at all

Negative evidence is the part that was missing, and it earns its keep twice.
It is genuinely informative — bouncing off Dark Souls says something bouncing
off nothing does not — and it removes a hack. When "not picked" conflated
dislike with never-played, a plain mean was wrong (a low pick dragged as hard
as a high pick lifted), so the estimate used the mean of the upper half with a
floor, justified at length. With dislike stated outright, that ambiguity is
gone and a plain weighted mean is both simpler and more honest.

A disliked game contributes a *reflected* observation at half weight: bouncing
off osu! (micro 0.98) is weak evidence for preferring low micro, and bouncing
off Animal Crossing (micro 0.12) is weak evidence for preferring more. Half
weight because a person can dislike a game for reasons this model knows nothing
about — monetisation, art style, the friend who made them play it.
"""

import math
from functools import cache
from dataclasses import dataclass, field
from typing import Any

import yaml

from r3m import db, scoring
from r3m.config import ROOT

DIMENSIONS = ("micro", "meso", "macro")

# How far from the middle a game sits before an answer about it says anything.
#
# Retained for `suggest_for` and the retry hook, which pick games to *serve*.
# It is no longer how evidence is weighed: see `opportunity`.
INFORMATIVE = 0.25

# A game whose largest demand is below this presents no demand at all, and the
# absence is then the thing on offer. See `opportunity`.
LOW_CORNER = 0.35
# Opportunity a dimension must accumulate before it counts as read, in the
# units `opportunity` returns: each game hands over at most one unit, split
# across the three dimensions.
#
# PROVISIONAL. 0.5 since the one-unit rule (2026-09-29), from 1.0 when a game
# could hand over up to a unit on *each* dimension. Chosen inside the window
# the two estimator tests leave -- Sergi's builders session must leave meso
# unread (it accumulates 0.44), the relaxed player must read micro (0.59) --
# which means the threshold is set by the same fixtures that check it. Nothing
# independent calibrates it yet; panel round 2 should.
#
# The fill-stage rates below are history. Re-measured 2026-09-29 on the Opus
# 5.5 labels, loving random picks: the fill stage runs for 2% of five-pick
# sessions at the old 1.0 and 0% here, from panel round 1's cards or the whole
# deck, and never at eight picks or more. Random picks are not how people
# pick, so these say little either way.
#
# Was a count of answers. A count cannot express the thing that broke: three
# games can be answered about and still offer nothing to answer *with*.
#
# Raised from 2 once the grid replaced the three-item opener. A 28-card grid
# hands over many more picks than a handful of single cards did, and at 2 a
# typical grid cleared every dimension outright -- which skipped the fill stage
# almost always, and called an axis read on two observations. Measured over
# random picks from the grid, the fill stage now runs for 84% of five-pick
# sessions and 32% of eight-pick ones, and someone who tapped twelve games has
# genuinely been read and skips it.
NEEDED = 0.5
# Dislike is real evidence, but noisier than delight.
DISLIKE_WEIGHT = 0.5
# How far under a disliked game's demand the dislike places the player.
DISLIKE_MARGIN = 0.05

# What a player can say made a love stick (docs/quiz-chain.md §5). Only the
# first is about the game's demand; the rest are real reasons to love a game
# that no champion can deliver, so for matching they are noise.
LOVE_REASONS = ("gameplay", "people", "world", "nostalgia", "what_i_had")
# What put them off. The last two cancel the dislike: "never really played it"
# means it was never evidence, "not the gameplay" means it was about the art or
# the setting, which says nothing about the three dimensions.
DISLIKE_REASONS = ("gameplay", "never_played", "not_gameplay")
# Where a person reads them. One tap each, so short, and in the player's words.
REASON_LABELS = {
    "love": {
        "gameplay": "How it plays",
        "people": "The people I played with",
        "world": "The world or the story",
        "nostalgia": "Nostalgia",
        "what_i_had": "It was what I had",
    },
    "dislike": {
        "gameplay": "How it plays",
        "never_played": "I never really played it",
        "not_gameplay": "Something else - the look, the setting",
    },
}
WHY_QUESTION = {"love": "What made it stick?", "dislike": "What put you off?"}

# How much a love counts when nobody asked why, by how easily the game is loved
# for something other than its demand (bank/bias.yaml). Starting points, not
# fits: round 2 of the panel measures how often loves of each level turn out to
# be about the gameplay, and these follow that. Unrated games get no discount --
# no prior is better than an invented one.
UNCONFIRMED = {"low": 1.0, "medium": 0.75, "high": 0.4}


def love_weight(row: dict[str, Any], reason: str | None) -> float:
    if reason == "gameplay":
        return 1.0
    if reason in LOVE_REASONS:
        return 0.0
    return UNCONFIRMED.get(row.get("bias"), 1.0)


def dislike_weight(reason: str | None) -> float | None:
    """Multiplier on DISLIKE_WEIGHT; None removes the dislike altogether."""
    if reason == "never_played":
        return None
    if reason == "not_gameplay":
        return 0.0
    return 1.0


def opportunity(row: dict[str, Any], dimension: str) -> float:
    """How much chance this game gave the player to express a taste here.

    One game, one unit of evidence (2026-09-29). A game's opportunities sum to
    at most 1 across the three dimensions, split by demand: CS2 spreads its
    unit over all three, osu! puts nearly all of it on micro. Before, each
    dimension got up to a unit of its own, and a low-corner game got about
    0.82 on every one -- one Solitaire answer weighed like two and a half
    full-demand games, and displaced four of a read player's top five.

    A game's coordinate on a dimension is how much *demand* it presents there
    (anchors/games.yaml, on converting Surnex's categories: his groupings are
    about proportion, this scale is about magnitude). Demand presented is
    therefore also opportunity offered -- Factorio has no opponent, so loving
    it expresses nothing about meso, not because low coordinates were decided
    to be weak evidence but because there was nothing there to love or reject.

    One clause, stated as a claim rather than bolted on: a game low on every
    dimension presents a different thing -- the absence of demand itself --
    and loving *that* is evidence for a low-demand taste. It is why Animal
    Crossing is informative about a relaxed player and Factorio is not
    informative about meso, though both score about 0.13 on it. That unit is
    spread evenly: what it says -- no demand here -- is the same about all
    three, whatever the small differences in how little each is asked for.
    """
    presence = max(row[d] for d in DIMENSIONS)
    if presence < LOW_CORNER:
        return (1.0 - presence) / 3
    return float(row[dimension]) / max(1.0, sum(row[d] for d in DIMENSIONS))



def demand(row: dict[str, Any], dimension: str) -> float:
    """How much of this one dimension the game presents.

    Distinct from `opportunity`, and the difference is the low-corner clause.
    Loving Minecraft creative is real evidence -- for a low-demand taste
    across the board -- so its *opportunity* is high on every dimension. But
    it cannot settle meso specifically, because it contains none. Weighing
    evidence asks what a game can tell us; choosing what to serve asks what
    this dimension needs, and only the second wants the raw coordinate.
    """
    return float(row[dimension])


@dataclass(frozen=True)
class DimensionEstimate:
    value: float
    # Weighted: a loved game counts 1, a disliked one DISLIKE_WEIGHT.
    informative: float

    @property
    def read(self) -> bool:
        return self.informative >= NEEDED


@dataclass(frozen=True)
class Estimate:
    loved: list[dict[str, Any]] = field(default_factory=list)
    disliked: list[dict[str, Any]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    dimensions: dict[str, DimensionEstimate] = field(default_factory=dict)

    @property
    def point(self) -> tuple[float, float, float]:
        return tuple(self.dimensions[d].value for d in DIMENSIONS)  # type: ignore[return-value]

    @property
    def unread(self) -> list[str]:
        return [d for d in DIMENSIONS if not self.dimensions[d].read]

    @property
    def answered(self) -> list[str]:
        return [g["game_id"] for g in (*self.loved, *self.disliked)]


def dislike_target(row: dict[str, Any], current: dict[str, float]) -> tuple[str, float] | None:
    """The one (dimension, value) a dislike argues for, or None if it argues nothing.

    A dislike rejects the demand that game presented and nothing else: bouncing
    off osu! says you wanted less execution, and says nothing about mind-games
    or macro, because osu! never asked for any. So a game speaks only where it
    presents demand -- the rule that made loving Factorio silent on meso,
    applied to dislikes. A low-corner dislike therefore argues nothing:
    bouncing off Solitaire rejects nothing, because nothing was asked. (The
    real case, "too shallow", belongs to an explicit reason.)

    And it says *too much on at least one* presented dimension -- an OR, not
    an AND. If the loves already put the player below the game on any of them,
    the dislike is explained and carries no position. If nothing explains it,
    it corrects only the dimension that needs the smallest move to explain it,
    to just under what was offered. Which dimension it really was, the why
    question can name later; this only declines to guess more than it must.

    History, 2026-09-29: the target was the reflection 1 - x, which read a
    micro-0.51 player disliking osu! as wanting micro 0.07. Then, for one day,
    "below what was offered on every presented dimension", which dragged the
    micro of a player who had disliked a game for its meso; in the simulation
    it moved a dimension away from the truth 64-83% of the times it moved one.
    """
    presented = [d for d in DIMENSIONS if row[d] >= LOW_CORNER and d in current]
    if not presented:
        return None
    ceiling = {d: row[d] - DISLIKE_MARGIN for d in presented}
    if any(current[d] <= ceiling[d] for d in presented):
        return None
    d = min(presented, key=lambda d: current[d] - ceiling[d])
    return d, max(0.0, ceiling[d])


def estimate(
    loved: list[str],
    disliked: list[str] | None = None,
    rows: list[dict[str, Any]] | None = None,
    reasons: dict[str, str] | None = None,
    scale: dict[str, float] | None = None,
) -> Estimate:
    """`scale` multiplies individual loves' weight -- the hook a robust
    estimator re-weights through (r3m.simulate). Nothing in serving passes it."""
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    by_id = {r["game_id"]: r for r in rows}
    disliked = disliked or []
    reasons = reasons or {}

    liked_rows = [by_id[g] for g in loved if g in by_id]
    # "Never really played it" was never evidence, so it leaves the dislikes
    # entirely rather than staying at zero weight.
    disliked_rows = [by_id[g] for g in disliked
                     if g in by_id and dislike_weight(reasons.get(g)) is not None]
    unknown = [g for g in (*loved, *disliked) if g not in by_id]

    if not liked_rows:
        # Without something enjoyed there is no positive anchor, and an
        # estimate built only from reflections of dislikes would be a guess
        # wearing a number.
        raise ValueError("need at least one game you enjoyed")
    love_w = {r["game_id"]: love_weight(r, reasons.get(r["game_id"])) * (scale or {}).get(r["game_id"], 1.0)
              for r in liked_rows}
    if not any(love_w.values()):
        # Every love was for the people, the world or the memory. That is no
        # signal about how they play, and filling it with the midpoint is the
        # imputation CLAUDE.md forbids -- so it is the same error as no love.
        raise ValueError(
            "every game you loved, you loved for something other than how it plays "
            "-- pick one you loved for the gameplay itself"
        )

    total = dict.fromkeys(DIMENSIONS, 0.0)
    weight = dict.fromkeys(DIMENSIONS, 0.0)
    for d in DIMENSIONS:
        for r in liked_rows:
            w = love_w[r["game_id"]] * opportunity(r, d)
            total[d] += w * r[d]
            weight[d] += w
    # Where the loves alone put the player. Dislikes are read against this,
    # not against a running value, so answer order cannot matter.
    current = {d: total[d] / weight[d] for d in DIMENSIONS if weight[d]}

    for r in disliked_rows:
        target = dislike_target(r, current)
        if target is None:
            continue
        d, value = target
        w = DISLIKE_WEIGHT * dislike_weight(reasons.get(r["game_id"])) * opportunity(r, d)
        total[d] += w * value
        weight[d] += w

    dims = {}
    for d in DIMENSIONS:
        # Accumulated opportunity *is* how much was read, so it is the same
        # number that weighs the evidence. Nothing to keep in step.
        dims[d] = DimensionEstimate(
            value=round(total[d] / weight[d], 2) if weight[d] else 0.5,
            informative=round(weight[d], 2),
        )

    return Estimate(loved=liked_rows, disliked=disliked_rows, unknown=unknown, dimensions=dims)


def suggest_for(dimension: str, exclude: list[str],
                rows: list[dict[str, Any]] | None = None, n: int = 5) -> list[dict[str, Any]]:
    """Games that would settle a dimension the answers left open.

    `exclude` must be everything already *served*, not just what was answered
    about: re-offering a game somebody just dismissed reads as not listening.
    """
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    candidates = [r for r in servable(rows) if r["game_id"] not in exclude]
    # By demand, not by distance from the middle. A game far *below* the
    # midpoint is as far from it as one far above and presents none of the
    # dimension, so offering it to settle that dimension asks a question it
    # cannot answer.
    #
    # Filtered, not just sorted: returning fewer is better than padding the
    # list with games that cannot settle anything. A bank thin on a dimension
    # should say so by offering less, which is also the signal that the bank
    # needs that pole filled.
    useful = [r for r in candidates if demand(r, dimension) >= 0.5 + INFORMATIVE]
    return sorted(useful, key=lambda r: -demand(r, dimension))[:n]


def champions_for(est: Estimate, n: int = 5) -> list[scoring.Match]:
    return scoring.neighbourhood(est.point, n=n)


# Three openers, widely recognised and far apart in the space: creative
# Minecraft is low on everything, Elden Ring is micro+macro, Among Us is meso.
# Placeholder until reach data exists — the real rule weights candidates by how
# many people have played them as well as by how much the answer would settle.
OPENER = ("minecraft-creative", "elden-ring", "among-us")

MAX_ITEMS = 10


def next_item(
    served: list[str],
    loved: list[str],
    disliked: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """The next game to ask about, or None when the quiz should stop."""
    by_id = {r["game_id"]: r for r in servable(rows)}
    if len(served) >= MAX_ITEMS:
        return None

    for game_id in OPENER:
        if game_id not in served and game_id in by_id:
            return by_id[game_id]

    target = "micro"
    if loved:
        est = estimate(loved, disliked, rows=rows)
        if not est.unread:
            return None
        target = min(est.unread, key=lambda d: est.dimensions[d].informative)

    candidates = [r for gid, r in by_id.items() if gid not in served]
    if not candidates:
        return None
    return max(candidates, key=lambda r: demand(r, target))


# What each dimension is called where a person can see it. The internal names
# are Surnex's and stay that way in the data; "meso 0.62" is meaningless to
# someone who has never read the model.
LABELS = {
    "micro": ("Execution", "aim, timing, and hitting things precisely"),
    "meso": ("Reading people", "predicting, baiting, and outguessing an opponent"),
    "macro": ("Planning", "where to be, what to build toward, when to commit"),
}

# Above this a dimension reads as "high", below its mirror as "low". Matches
# INFORMATIVE so the same answer that counts as evidence also counts as a
# trait worth naming.
STRONG = 0.5 + INFORMATIVE


def explain(est: Estimate, match: scoring.Match) -> str | None:
    """One sentence on why this champion, in the player's terms.

    Picks the dimension the player is most decided about *and* the champion
    agrees on — being sure about something the champion does not share is not
    a reason. Returns None when there is no such trait, because inventing a
    reason is worse than omitting one.

    Only read dimensions qualify: what was not read is said, not filled
    (CLAUDE.md). Until 2026-09-30 an unread axis could explain a match -- "you
    lean away from execution" above a reading that said execution was not
    enough to tell.
    """
    best, best_score = None, 0.0
    for i, d in enumerate(DIMENSIONS):
        if not est.dimensions[d].read:
            continue
        mine, theirs = est.dimensions[d].value, match.point[i]
        decided = abs(mine - 0.5)
        if decided < INFORMATIVE:
            continue
        agreement = decided - abs(mine - theirs)
        if agreement > best_score:
            best, best_score = d, agreement
    if best is None:
        return None

    name, gloss = LABELS[best]
    high = est.dimensions[best].value >= 0.5
    return (
        f"You lean {'into' if high else 'away from'} {name.lower()} — {gloss}. "
        f"{match.name} {'does too' if high else 'asks little of it either'}."
    )


# ---------------------------------------------------------------------------
# Staged flow: grid -> fill -> specify (docs/quiz-flow.md)
# ---------------------------------------------------------------------------

# Cards in the opening grid. Larger than feels right from one-at-a-time
# thinking, where every served item costs a decision -- a grid is scanned, so
# an unrecognised card costs a glance. Showing more buys coverage of the space
# almost free, and at 28 of 43 the hand-curation problem mostly dissolves.
GRID = 28
# How much spread a card with cover art may give up to displace one without.
# High enough to only swap near-ties: a genuinely isolated corner of the space
# is still taken text-only rather than left uncovered.
ART_SLACK = 0.85
# Single cards after the grid. Zero to four, and often zero: this stage only
# runs for dimensions the grid left unread.
FILL_MAX = 4


def grid(rows: list[dict[str, Any]] | None = None, n: int = GRID) -> list[dict[str, Any]]:
    """The opening grid: a farthest-point traversal of the bank.

    Take the most extreme game, then repeatedly take whichever is furthest
    from everything already picked. Covers the poles by construction rather
    than by judgement, which is the half of the problem that is decidable --
    recognisability is the other half and needs reach data the bank does not
    carry yet.

    Extremes come first, so the *tail* is the middle of the space, which is
    where the mainstream lives. That is the right way round: the grid absorbs
    the obscure items, where a card costs a glance, and `fill_item` inherits
    the recognisable ones, where an item costs a decision.

    Cover art breaks the tie. Distance alone concentrated the art gap into the
    grid -- the poles are disproportionately the Nintendo, Blizzard and mobile
    titles Steam does not carry, so 12 of 28 cards came out text-only while the
    games it discarded mostly had covers. Where a card with art is nearly as
    far out as the best candidate, it is taken instead: the grid is the one
    screen that has to read as a deck, and a coverage difference that small is
    not worth half the screen looking unfinished.
    """
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    return spread_order(servable(rows), n)


def spread_order(pool: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """grid's farthest-point traversal over a pool the caller already chose.

    Split out so the card selector can order its own pool: grid() filters by
    the current SERVING mode, and a selector calling grid() had its pool quietly
    narrowed to panel round 1's cards.
    """
    if not pool:
        return []

    def gap(a: dict[str, Any], b: dict[str, Any]) -> float:
        return sum((a[d] - b[d]) ** 2 for d in DIMENSIONS) ** 0.5

    middle = {d: 0.5 for d in DIMENSIONS}
    picked = [max(pool, key=lambda r: gap(r, middle))]
    rest = [r for r in pool if r is not picked[0]]
    while rest and len(picked) < n:
        spread = {id(r): min(gap(r, p) for p in picked) for r in rest}
        best = max(rest, key=lambda r: spread[id(r)])
        nxt = best
        if not best.get("steam_appid"):
            withart = [r for r in rest
                       if r.get("steam_appid")
                       and spread[id(r)] >= ART_SLACK * spread[id(best)]]
            if withart:
                nxt = max(withart, key=lambda r: spread[id(r)])
        picked.append(nxt)
        rest.remove(nxt)
    return picked


# What the quiz may put on screen, until the card selector exists
# (docs/quiz-chain.md §4, "a card is a question"). Decided 2026-09-29.
#
# "panel-round-1": exactly the cards panel round 1 saw. Rounds deal its 28 grid
# cards -- the 7 nobody tapped included, as they were shown then -- and fill
# draws from the same 43-game bank round 1 filled from. Two reasons. Round 2
# then tests what actually changed, the evidence mechanics (played / never,
# fine, why), not a new card set. And labels likely track fame: games-v2 labels
# from the model's own knowledge of a title, so the obscure extremes a 300-game
# bank surfaces are both less recognisable and less reliably labelled.
#
# "bank": the whole labelled deck (servable_bank below), for when a selector
# chooses cards by recognition as well as spread.
SERVING = "panel-round-1"
# Reconstructed 2026-09-29 as the 43-game bank minus the 15 it never showed,
# and verified against production: every game tapped in round 1 is one of these
# 28 or one of the two fill cards it served (osu, tekken).
PANEL_ROUND_1_CARDS = frozenset({
    "age-of-empires-2", "among-us", "animal-crossing", "apex-legends", "balatro",
    "brawlhalla", "chess", "cookie-clicker", "cs2", "dota-2", "elden-ring",
    "factorio", "fall-guys", "gang-beasts", "geometry-dash", "hades",
    "hearthstone", "liars-bar", "mario-64", "marvel-rivals", "minecraft-creative",
    "phasmophobia", "pokemon-vgc", "rocket-league", "stardew-valley", "tetris-99",
    "valheim", "wow",
})
PANEL_ROUND_1_BANK = PANEL_ROUND_1_CARDS | frozenset({
    "candy-crush", "getting-over-it", "jump-king", "league-of-legends",
    "mario-kart", "osu", "overwatch", "poly-bridge", "rainbow-six", "smash-bros",
    "street-fighter", "tekken", "tetris", "tft", "valorant",
})


def servable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Games that may appear as a card, under the current SERVING mode."""
    if SERVING == "panel-round-1":
        return [r for r in rows if r["game_id"] in PANEL_ROUND_1_BANK]
    return servable_bank(rows)


def servable_bank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Games that may appear as a card: the deck tier, in the bank.

    A deep entry (a mode or a platform game, bank/hand.yaml) is what a deck pick
    opens into and never a first-screen card -- with one exception: while its
    parent has no label, it stands in for the parent. Minecraft and Pokémon are
    labelled only through their deep entries (creative, VGC) until the new deck
    is labelled; excluding those would silently take Minecraft off the grid.
    The stand-in ends by itself the moment the parent has a label. Platforms
    (Roblox, Garry's Mod) have no parent and never stand in.
    """
    labelled = {r["game_id"] for r in rows}
    return [
        r for r in rows
        if r.get("in_bank", True) and (
            r.get("tier", "deck") == "deck"
            or (r.get("parent_id") and r["parent_id"] not in labelled)
        )
    ]


# Rounds of the recognition sweep (docs/quiz-chain.md §3). The same order for
# everyone for now: with ~47 labelled games, three rounds already show three
# quarters of the bank, so there is nothing to choose between. Rounds become
# per-player once the new deck is labelled.
# Fourteen, not twelve: with the original 50-game bank, the 42 games people
# did tap in the panel fit three rounds exactly, so none was dropped for its
# position. Seven rows of two on a phone. A hard cap, not a target.
ROUND = 14
MAX_ROUNDS = 3
# Recognised games (loved, fine or disliked) after which, if every dimension is
# also read, another round costs more attention than it returns.
ENOUGH_RECOGNISED = 8
# Shown in panel round 1 (2026-09-26, 16 sessions, the whole 28-card grid) and
# tapped by nobody, loved or bounced. That is the only recognition evidence the
# project has for the segment, so these go to the back of the rounds instead of
# spending round 1 on cards people pass over. Spread alone put two of them in
# round 1. A proper recognition order (Steam reach, panel tap rates) comes with
# the labelled deck; this is the part the evidence already settles.
NEVER_TAPPED = frozenset({
    "animal-crossing", "cookie-clicker", "fall-guys", "marvel-rivals",
    "pokemon-vgc", "stardew-valley", "tetris-99",
})


def next_round(
    index: int,
    *,
    played: list[str],
    loved: list[str],
    disliked: list[str],
    reasons: dict[str, str],
    rows: list[dict[str, Any]],
    shown: list[str] | None = None,
    champions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    """Cards for round `index` (0-based), or None when the sweep should stop.

    Under SERVING = "selector" the choice is select_round's, which needs what
    was already shown and the champion rows; the fixed modes below do not.

    The first round always runs. After it the sweep stops once enough games are
    recognised and every dimension is read -- so someone who has played a lot
    answers one round, someone who recognises little sees two or three.
    """
    if SERVING == "selector":
        if champions is None:
            with db.connect() as conn:
                champions = db.champion_points(conn)
        return select_round(index, shown=shown or [], played=played, loved=loved,
                            disliked=disliked, reasons=reasons, rows=rows, champions=champions)

    # Dealt like a deck, not cut in order. The spread order runs from the
    # extremes to the middle, and the middle is where the mainstream lives
    # (grid's docstring): cut into consecutive rounds, CS2, League and Valorant
    # all fell past round 3 and were never shown. Dealt round-robin, every
    # round is a cross-section -- extremes and mainstream -- so round 1 alone is
    # a fair sample for a player who stops after it.
    spread = grid(rows, n=len(rows))
    if SERVING == "panel-round-1":
        # Round 1's grid, dealt into rounds, never-tapped cards in their place:
        # changing which cards show would confound the test of the mechanics.
        main = [r for r in spread if r["game_id"] in PANEL_ROUND_1_CARDS]
        last = []
    else:
        main = [r for r in spread if r["game_id"] not in NEVER_TAPPED]
        last = [r for r in spread if r["game_id"] in NEVER_TAPPED]
    count = min(MAX_ROUNDS, max(1, -(-len(main) // ROUND)))
    # Capped at ROUND: dealt without a cap, a 300-game bank made three rounds
    # of ~100 cards (2026-09-29, the day the deck was labelled). Which ROUND
    # cards a bank that size should show is the recognition question
    # (docs/quiz-chain.md §4, "a card is a question"); until that selector
    # exists, each round takes the first ROUND of its dealt pile.
    rounds = [main[i::count][:ROUND] for i in range(count)]
    # Never-tapped cards only fill room left in the last round. The rest stay in
    # the bank for the fill stage, which serves them only when they would read
    # a dimension -- appended outright, they made round 3 twenty cards long.
    rounds[-1] = rounds[-1] + last[:max(0, ROUND - len(rounds[-1]))]
    rounds = [r for r in rounds if r]
    if index >= len(rounds):
        return None
    # Panel round 2 shows every player all of round 1's cards: the point of
    # serving them is a card set identical across players and to round 1, and
    # a stop that depends on this build's estimator would make the replay log
    # depend on it too. Stopping early there cut the quiz to 14 of 28 cards for
    # nearly everyone once NEEDED fell to 0.5 (2026-09-30, first live session).
    if SERVING != "panel-round-1" and index > 0 and len(played) >= ENOUGH_RECOGNISED and loved:
        try:
            est = estimate(loved, disliked, rows=rows, reasons=reasons)
        except ValueError:
            est = None
        if est is not None and not est.unread:
            return None
    return rounds[index]


# ---------------------------------------------------------------------------
# The card selector (docs/quiz-chain.md §4, "a card is a question").
# SERVING = "selector". Built 2026-09-29, not yet switched on: panel round 2
# serves round 1's cards so it tests the evidence mechanics alone.
# ---------------------------------------------------------------------------

# Recognition prior by hand tier (bank/renown.yaml) -- has a typical player in
# the segment ever played it?
RENOWN_PRIOR = {"universal": 0.85, "wide": 0.55, "niche": 0.25}
# Steam lifetime reach mapped onto the same scale, log-linearly: the bank's
# floor (20k reviews) reads as niche, 5M and above as universal. Valheim
# (~500k) lands near 0.6.
REACH_FLOOR, REACH_CEIL = 20_000, 5_000_000
PRIOR_LOW, PRIOR_HIGH = 0.25, 0.85
# Round 1 is the same for everyone and drawn only from games at least this
# likely to be recognised: before a single answer there is nothing to adapt
# to, and an obscure extreme is both a wasted glance and a weakly-known label.
ROUND_ONE_FLOOR = 0.5
# Later rounds: this share of each round is chosen for spread alone, among
# games at least EXPLORE_FLOOR recognisable. The recognition estimate is learnt
# from what people were shown, so it must never be the only door.
EXPLORE_SHARE = 1 / 3
EXPLORE_FLOOR = 0.4
# Given a game was played, how likely each verdict is. Before any answer the
# flat starting values; after, it depends on where the card sits relative to
# the player's current point -- a far-off card is more often "fine" or disliked
# than loved, and "fine" moves nothing. Panel round 2 measures all of these.
P_LOVED, P_DISLIKED = 0.6, 0.4
# Distance from the current point at which loving a card becomes as likely as
# not, and how sharply that falls off. 0.35 is about seven champion-widths.
LOVE_MIDPOINT, LOVE_SOFTNESS = 0.35, 0.08
# value = recognition ** RECOGNITION_POWER x information. 1 is the plain
# product; 0 ignores recognition (inside the field SCORED already narrowed);
# above 1 leans on it. The dial the simulation sweeps (r3m simulate).
RECOGNITION_POWER = 1.0


def verdict_odds(row: dict[str, Any], point: tuple[float, float, float] | None) -> tuple[float, float]:
    """(P loved, P disliked) for a played card, given the current point."""
    if point is None:
        return P_LOVED, P_DISLIKED
    d = math.dist(point, (row["micro"], row["meso"], row["macro"]))
    loved = 0.1 + 0.65 / (1 + math.exp((d - LOVE_MIDPOINT) / LOVE_SOFTNESS))
    return loved, 0.5 * (1 - loved)
# Cards scored in full each round. Scoring is two estimates and two
# neighbourhoods per card, so the field is narrowed by recognition first.
SCORED = 60


def recognition_prior(row: dict[str, Any]) -> float:
    """P(a player in the segment has played this), before any answers."""
    if row.get("renown") in RENOWN_PRIOR:
        return RENOWN_PRIOR[row["renown"]]
    reach = row.get("reach")
    if reach:
        span = math.log10(REACH_CEIL) - math.log10(REACH_FLOOR)
        t = (math.log10(reach) - math.log10(REACH_FLOOR)) / span
        return PRIOR_LOW + (PRIOR_HIGH - PRIOR_LOW) * min(1.0, max(0.0, t))
    return PRIOR_LOW


def breadth(shown: list[str], played: list[str], by_id: dict[str, dict[str, Any]]) -> float:
    """How much more (or less) this player recognises than the priors expect.

    A ratio of actual to expected recognitions over the cards shown, smoothed
    by one so the first round cannot swing it far. Someone who has played more
    of what they were shown than a typical player would is likely to know the
    next card too.
    """
    expected = sum(recognition_prior(by_id[g]) for g in shown if g in by_id)
    actual = sum(1 for g in shown if g in played)
    return (actual + 1) / (expected + 1)


def recognition(row: dict[str, Any], k: float) -> float:
    p = recognition_prior(row)
    odds = p / (1 - p) * k
    return odds / (1 + odds)


def information(
    row: dict[str, Any],
    loved: list[str],
    disliked: list[str],
    reasons: dict[str, str],
    rows: list[dict[str, Any]],
    champions: list[dict[str, Any]],
    now: set[str] | None,
    est: "Estimate | None",
) -> float:
    """How much answering this card would change the result, 0 to 1.

    Two parts, equally weighted. The expected share of the top five champions
    its answer would displace (loved or disliked, weighted by how often a
    played game is each) -- the same test a follow-up question has to pass. And
    how much of the still-unread dimensions it would read: before anything is
    loved there is no top five to move, and reading an unread dimension is
    then the whole value.
    """
    g = row["game_id"]
    p_love, p_hate = verdict_odds(row, est.point if est is not None else None)
    if now is None:
        shift = p_love
    else:
        love = _top(loved + [g], disliked, reasons, rows, champions)
        hate = _top(loved, disliked + [g], reasons, rows, champions)
        shift = (p_love * len(now - (love or now)) + p_hate * len(now - (hate or now))) / 5
    need = {d: 1.0 if est is None else max(0.0, NEEDED - est.dimensions[d].informative) / NEEDED
            for d in DIMENSIONS}
    # demand, not opportunity: choosing what to serve asks what a dimension
    # needs (see demand's docstring). opportunity rates a low-demand game as
    # reading every dimension at once, which put tic-tac-toe and Solitaire at
    # the top of every player's round 2.
    reads = sum(demand(row, d) * need[d] for d in DIMENSIONS) / max(1e-9, sum(need.values()))
    return 0.5 * shift + 0.5 * (reads if any(need.values()) else 0.0)


def select_round(
    index: int,
    *,
    shown: list[str],
    played: list[str],
    loved: list[str],
    disliked: list[str],
    reasons: dict[str, str],
    rows: list[dict[str, Any]],
    champions: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """One round of the recognition sweep under the selector, or None to stop."""
    pool = [r for r in servable_bank(rows) if r["game_id"] not in set(shown)]
    if index >= MAX_ROUNDS or not pool:
        return None
    if index == 0:
        known = [r for r in pool if recognition_prior(r) >= ROUND_ONE_FLOOR]
        return spread_order(known, ROUND)

    est = None
    if loved:
        try:
            est = estimate(loved, disliked, rows=rows, reasons=reasons)
        except ValueError:
            est = None
    if len(played) >= ENOUGH_RECOGNISED and est is not None and not est.unread:
        return None

    by_id = {r["game_id"]: r for r in rows}
    k = breadth(shown, played, by_id)
    now = _top(loved, disliked, reasons, rows, champions) if loved else None
    field = sorted(pool, key=lambda r: -recognition(r, k))[:SCORED]
    value = {r["game_id"]: recognition(r, k) ** RECOGNITION_POWER * information(
        r, loved, disliked, reasons, rows, champions, now, est) for r in field}

    n_explore = round(ROUND * EXPLORE_SHARE)
    chosen = sorted(field, key=lambda r: -value[r["game_id"]])[:ROUND - n_explore]

    # Exploration: farthest from everything shown or chosen, among games a
    # player could plausibly know -- spread, not value.
    def gap(a: dict[str, Any], b: dict[str, Any]) -> float:
        return sum((a[d] - b[d]) ** 2 for d in DIMENSIONS) ** 0.5
    seen = [by_id[g] for g in shown if g in by_id] + chosen
    taken = {r["game_id"] for r in chosen}
    candidates = [r for r in pool if r["game_id"] not in taken
                  and recognition(r, k) >= EXPLORE_FLOOR]
    for _ in range(n_explore):
        if not candidates:
            break
        far = max(candidates, key=lambda r: min((gap(r, s) for s in seen), default=1.0))
        chosen.append(far)
        seen.append(far)
        candidates.remove(far)
    return chosen


# Follow-up questions in the whole quiz. Each costs a screen, so they go where
# the answer changes the result and nowhere else.
WHY_MAX = 3
# Top-five champions an answer must be able to displace to be worth asking.
WHY_IMPACT = 1


def _top(loved: list[str], disliked: list[str], reasons: dict[str, str],
         rows: list[dict[str, Any]], champions: list[dict[str, Any]]) -> set[str] | None:
    try:
        est = estimate(loved, disliked, rows=rows, reasons=reasons)
    except ValueError:
        return None
    return {m.champion_id for m in scoring.neighbourhood(est.point, n=5, rows=champions)}


def why_next(
    loved: list[str],
    disliked: list[str],
    reasons: dict[str, str],
    rows: list[dict[str, Any]],
    champions: list[dict[str, Any]],
    *,
    asked: int = 0,
    skip: list[str] | None = None,
) -> dict[str, Any] | None:
    """The one follow-up worth asking next, or None.

    `skip`: games already asked about and left unanswered. In panel round 2
    every love is asked after its round, so what reaches here is mostly
    dislikes -- and a love someone chose not to explain is not asked again.

    Candidates: loves of bias-prone games (high, then medium) and dislikes,
    none already answered. Low-bias loves are never asked -- nobody loves osu!
    for its story. A candidate is worth a screen only if its two possible
    answers lead to different top-five champions: counting it in full against
    not at all for a love, keeping against removing for a dislike. Whichever
    moves the most is asked; ties go to high loves, then dislikes, then medium
    loves. An answer that could remove the last counting love moves everything,
    so it is always worth asking.
    """
    if asked >= WHY_MAX:
        return None
    by_id = {r["game_id"]: r for r in rows}
    candidates: list[tuple[int, int, str, str]] = []
    for g in loved:
        bias = by_id.get(g, {}).get("bias")
        if g in reasons or g in (skip or ()) or bias not in ("high", "medium"):
            continue
        yes = _top(loved, disliked, {**reasons, g: "gameplay"}, rows, champions)
        no = _top(loved, disliked, {**reasons, g: "people"}, rows, champions)
        impact = 5 if no is None else len(yes - no) if yes else 0
        candidates.append((impact, 0 if bias == "high" else 2, g, "love"))
    for g in disliked:
        if g in reasons or g in (skip or ()) or g not in by_id:
            continue
        keep = _top(loved, disliked, {**reasons, g: "gameplay"}, rows, champions)
        drop = _top(loved, disliked, {**reasons, g: "never_played"}, rows, champions)
        impact = len(keep - drop) if keep and drop else 0
        candidates.append((impact, 1, g, "dislike"))

    worth = [c for c in candidates if c[0] >= WHY_IMPACT]
    if not worth:
        return None
    _, _, game, kind = max(worth, key=lambda c: (c[0], -c[1]))
    options = LOVE_REASONS if kind == "love" else DISLIKE_REASONS
    return {"game_id": game, "kind": kind, "options": list(options)}


def fill_item(
    served: list[str],
    loved: list[str],
    disliked: list[str],
    rows: list[dict[str, Any]],
    asked: int = 0,
    reasons: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Stage 2: one more card, or None when there is nothing left to read.

    Unlike `next_item` there is no opener -- the grid was the opener -- and the
    budget counts only what this stage served, not the whole grid. Returns None
    the moment every dimension is read, so the common case is that this stage
    does not run at all.
    """
    if asked >= FILL_MAX or not loved:
        return None
    try:
        est = estimate(loved, disliked, rows=rows, reasons=reasons)
    except ValueError:
        return None  # no love counts: nothing to fill toward, the result says so
    if not est.unread:
        return None
    target = min(est.unread, key=lambda d: est.dimensions[d].informative)

    candidates = [r for r in servable(rows) if r["game_id"] not in served]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: demand(r, target))
    # A card that presents none of the open dimension is not worth a screen:
    # answering about it, either way, leaves the dimension exactly as unread.
    return best if demand(best, target) >= 0.5 + INFORMATIVE else None


# A pair isolates a dimension when the two games are far apart on it and close
# on the other two: everything but the target is controlled, so the answer
# reads as an opinion about the target alone.
PAIR_SPLIT = 0.35
PAIR_MATCH = 0.15
# Comparisons offered after the result. Small: this sharpens an answer the user
# has already been shown, and a fourth screen of it stops being a refinement.
SHARPEN_MAX = 3
# How far to nudge a dimension when asking whether it changes the answer. Set
# by the space, not chosen: the median distance between a champion and its
# nearest neighbour is 0.051 and scoring.CLOSE is 0.10, so this is the
# smallest move that can reorder a list.
NUDGE = 0.05
# Fraction of the gap to the winner that one comparison pulls, before the cap.
# Deliberately small. Pairs are contrastive by construction, so the winner is
# always far from the current estimate -- at half the gap a single comparison
# saturated the cumulative cap, which made every answer move the same distance
# and turned the cap into the only parameter. At a fifth, one answer nudges by
# about NUDGE (enough to reorder the list, not to relocate it) and it takes
# roughly a full SHARPEN_MAX of agreeing answers to reach the ceiling.
#
# 0.15 since 2026-09-30, when comparisons moved before the result and the
# cumulative cap came off. Simulated at 70 cards, cap off: at 0.2, 9.8% of
# single comparisons moved the point more than scoring.CLOSE; at 0.15, 1.1%,
# with error 0.313 -> 0.286 over the comparisons -- the same gain the capped
# 0.2 gave (0.287). Each comparison is still capped at CLOSE on its own, so
# none can relocate the point alone.
COMPARISON_PULL = 0.15


def contrastive(a: dict[str, Any], b: dict[str, Any]) -> str | None:
    """The dimension this pair isolates, or None if it isolates nothing."""
    for d in DIMENSIONS:
        if abs(a[d] - b[d]) >= PAIR_SPLIT and all(
            abs(a[o] - b[o]) <= PAIR_MATCH for o in DIMENSIONS if o != d
        ):
            return d
    return None


def sensitivity(est: "Estimate", n: int = 5) -> dict[str, int]:
    """Per dimension, how many of the top n champions a nudge displaces.

    The question worth spending a user's attention on is not "which dimension
    am I least sure about" but "which uncertainty actually changes what I would
    tell you". Those are different axes, and only the second one is worth a
    screen.
    """
    base = {(m.champion_id, m.role) for m in champions_for(est, n=n)}
    out = {}
    for i, d in enumerate(DIMENSIONS):
        worst = 0
        for sign in (1, -1):
            point = list(est.point)
            point[i] = min(1.0, max(0.0, point[i] + sign * NUDGE))
            moved = {(m.champion_id, m.role)
                     for m in scoring.neighbourhood(tuple(point), n=n)}
            worst = max(worst, len(base - moved))
        out[d] = worst
    return out


def pair_for(
    est: "Estimate", dimension: str, used: list[str] | None = None
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """A contrastive pair on `dimension`, drawn from what the player recognised.

    Drawn from answered games rather than the bank because a comparison can
    fail in a way a verdict cannot: serve two games the player has not played
    and the screen bought nothing, whereas "never played" is a valid answer to
    a verdict. Every game here carries a verdict, so both cards are known.

    Recognised, not loved. Restricting the pool to the loved set looked right
    -- "you liked both, which more" is the cleanest version of the question --
    but the grid broke it. A second pass that asks what you bounced off makes
    dislikes cheap to tap, and people mark many; those count toward a dimension
    being read, which closes the fill stage, while a loved-only pool stays tiny
    and closes this one too. Measured at three loved and eight disliked: the
    fill stage fired 6% of the time and a pair existed 24%. Both stages
    vanished for anyone who used the second pass the way it invites.

    Re-using answered games is not double-counting, provided the answer updates
    the point relatively (`apply_comparisons`) rather than landing as a fresh
    absolute observation. "Which would you go back to" is information a
    three-way verdict had no way to express, whichever verdicts those two games
    got.
    """
    used = used or []
    pool = [*est.loved, *est.disliked]
    best, widest = None, 0.0
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            if a["game_id"] in used or b["game_id"] in used:
                continue
            if contrastive(a, b) != dimension:
                continue
            split = abs(a[dimension] - b[dimension])
            if split > widest:
                best, widest = (a, b), split
    return best


def sharpen(
    est: "Estimate", used: list[str] | None = None
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """The dimension worth one more question, and a pair that reads it.

    Degrades by disappearing. If nothing in the loved set isolates the axis
    that matters, try the next axis; if nothing isolates any of them, offer no
    refinement at all -- the result already shown is complete, which is the
    whole reason this stage sits after it.
    """
    order = sorted(sensitivity(est).items(), key=lambda kv: -kv[1])
    for dimension, moved in order:
        if moved == 0:
            break  # nothing below this reorders anything either
        pair = pair_for(est, dimension, used=used)
        if pair:
            return dimension, *pair
    return None


def apply_comparisons(
    est: "Estimate",
    comparisons: list[dict[str, str]],
    rows: list[dict[str, Any]],
) -> "Estimate":
    """Fold pairwise answers into the point, each one bounded.

    Each comparison pulls COMPARISON_PULL of the gap to the winner's level on
    the dimension the pair isolates, and no single comparison moves the point
    more than scoring.CLOSE.

    Until 2026-09-30 comparisons came after the result and the *cumulative*
    displacement was capped at CLOSE: a deliberate underweighting, right only
    while the player watched a result they had already been shown rearrange.
    They now come before the reveal -- the player narrowing it down, not
    adjusting a shown answer -- so that cap came off, as this docstring said it
    would, and the bound moved to each answer.
    """
    by_id = {r["game_id"]: r for r in rows}
    delta = {d: 0.0 for d in DIMENSIONS}
    for c in comparisons:
        winner, loser = by_id.get(c.get("winner")), by_id.get(c.get("loser"))
        if not winner or not loser:
            continue
        d = c.get("dimension") or contrastive(winner, loser)
        if d not in DIMENSIONS:
            continue
        pull = COMPARISON_PULL * (winner[d] - est.dimensions[d].value)
        delta[d] += max(-scoring.CLOSE, min(scoring.CLOSE, pull))

    dims = {
        d: DimensionEstimate(
            value=round(min(1.0, max(0.0, est.dimensions[d].value + delta[d])), 2),
            informative=est.dimensions[d].informative,
        )
        for d in DIMENSIONS
    }
    return Estimate(loved=est.loved, disliked=est.disliked,
                    unknown=est.unknown, dimensions=dims)


# ---------------------------------------------------------------------------
# Deep dives (docs/quiz-chain.md §3, §4): how someone played a game they loved.
# ---------------------------------------------------------------------------

DEEP_DIVES_FILE = ROOT / "bank" / "deep_dives.yaml"
# One answer's pull on its axis. Below scoring.CLOSE, so like a comparison no
# single answer relocates the point; the two options of a question pull the
# same size in opposite directions, so a random answerer does not drift.
DEEP_DIVE_SIZE = {"small": 0.04, "medium": 0.08}
# Families asked about per session: two families is six questions at most,
# about thirty seconds.
DEEP_DIVE_FAMILIES = 2
# The two splits decided in docs/quiz-chain.md §2. Answers on them are logged
# and not applied: matching does not use the splits yet, and logged answers
# plus Riot-id mains are how split matching gets tested before it ships.
SPLITS = ("micro_split", "meso_split")


@cache
def deep_dives() -> dict[str, dict[str, Any]]:
    with DEEP_DIVES_FILE.open() as fh:
        return yaml.safe_load(fh)


def _question(qid: str) -> tuple[str, dict[str, Any]] | None:
    for family, f in deep_dives().items():
        for q in f["questions"]:
            if q["id"] == qid:
                return family, q
    return None


def deep_dive_next(
    loved: list[str],
    reasons: dict[str, str],
    answered: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """The next deep-dive question, or None.

    Only about games loved for the gameplay: a love named for the people, the
    world, nostalgia or what they had is not asked about -- the answer would
    describe a game the player did not choose for how it plays. A love nobody
    gave a reason for counts as gameplay, as it does in the estimate. Families
    in the order their first game was loved, at most DEEP_DIVE_FAMILIES.
    `answered` holds every question already put, answered or skipped.
    """
    asked = {a["question"] for a in answered}
    families: list[str] = []
    for g in loved:
        if reasons.get(g) not in (None, "gameplay"):
            continue
        for family, f in deep_dives().items():
            if g in f["games"] and family not in families:
                families.append(family)
    for family in families[:DEEP_DIVE_FAMILIES]:
        for q in deep_dives()[family]["questions"]:
            if q["id"] not in asked:
                return {"family": family, "name": deep_dives()[family]["name"], **q}
    return None


def apply_deep_dives(est: "Estimate", answered: list[dict[str, Any]]) -> "Estimate":
    """Fold deep-dive answers into the point: each moves its axis by its size,
    in its option's direction. Split answers and skips move nothing."""
    delta = {d: 0.0 for d in DIMENSIONS}
    for a in answered:
        found = _question(a.get("question", ""))
        if found is None or a.get("option") is None:
            continue
        _, q = found
        option = next((o for o in q["options"] if o["id"] == a["option"]), None)
        if option is None or q["axis"] in SPLITS or q["axis"] not in DIMENSIONS:
            continue
        delta[q["axis"]] += option["sign"] * DEEP_DIVE_SIZE[q["size"]]
    if not any(delta.values()):
        return est
    dims = {
        d: DimensionEstimate(
            value=round(min(1.0, max(0.0, est.dimensions[d].value + delta[d])), 2),
            informative=est.dimensions[d].informative,
        )
        for d in DIMENSIONS
    }
    return Estimate(loved=est.loved, disliked=est.disliked, unknown=est.unknown, dimensions=dims)


def settle(est: "Estimate", deep: list[dict[str, Any]], comparisons: list[dict[str, str]],
           rows: list[dict[str, Any]]) -> "Estimate":
    """Everything after the verdicts, in the order it is asked: deep dives,
    then comparisons, which pull relative to the point the dives left."""
    return apply_comparisons(apply_deep_dives(est, deep), comparisons, rows)
