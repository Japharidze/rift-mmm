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

from dataclasses import dataclass, field
from typing import Any

from r3m import db, scoring

DIMENSIONS = ("micro", "meso", "macro")

# How far from the middle a game sits before an answer about it says anything.
INFORMATIVE = 0.25
# Informative answers per dimension before it counts as read. A diversity
# floor, not a count: three micro-ish answers leave meso and macro unmeasured
# however many were served.
NEEDED = 2
# Dislike is real evidence, but noisier than delight.
DISLIKE_WEIGHT = 0.5


@dataclass(frozen=True)
class DimensionEstimate:
    value: float
    informative: int

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


def estimate(
    loved: list[str],
    disliked: list[str] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> Estimate:
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    by_id = {r["game_id"]: r for r in rows}
    disliked = disliked or []

    liked_rows = [by_id[g] for g in loved if g in by_id]
    disliked_rows = [by_id[g] for g in disliked if g in by_id]
    unknown = [g for g in (*loved, *disliked) if g not in by_id]

    if not liked_rows:
        # Without something enjoyed there is no positive anchor, and an
        # estimate built only from reflections of dislikes would be a guess
        # wearing a number.
        raise ValueError("need at least one game you enjoyed")

    dims = {}
    for d in DIMENSIONS:
        total = sum(r[d] for r in liked_rows)
        weight = float(len(liked_rows))
        for r in disliked_rows:
            total += DISLIKE_WEIGHT * (1.0 - r[d])
            weight += DISLIKE_WEIGHT
        informative = sum(
            1 for r in (*liked_rows, *disliked_rows) if abs(r[d] - 0.5) >= INFORMATIVE
        )
        dims[d] = DimensionEstimate(value=round(total / weight, 2), informative=informative)

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
    candidates = [r for r in rows
                  if r["game_id"] not in exclude and r.get("in_bank", True)]
    return sorted(candidates, key=lambda r: -abs(r[dimension] - 0.5))[:n]


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
    by_id = {r["game_id"]: r for r in rows if r.get("in_bank", True)}
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
    return max(candidates, key=lambda r: abs(r[target] - 0.5))


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
    """
    best, best_score = None, 0.0
    for i, d in enumerate(DIMENSIONS):
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
