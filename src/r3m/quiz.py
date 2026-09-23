"""Games a player picked -> an MMM point -> champions.

Equal weights across picks for the pilot (CLAUDE.md, open questions), but the
estimate is the mean of the **upper half** of them per dimension, not the mean
of all.

Picking a game is positive evidence that you enjoy that level of demand. Not
picking one is ambiguous — dislike and never-played are indistinguishable. A
plain mean treats those symmetrically, so a low pick drags the estimate down
exactly as hard as a high pick lifts it, which is wrong in a specific and
visible way: someone who plays osu! *and* Factorio *and* Among Us averages to
dead centre and is handed generic mid-range champions, when what they have
demonstrated is range across the whole space.

Measured against four personas, the upper-half mean was the only rule that
fixed that without breaking its opposite. `max` and the 75th percentile both
lift a relaxed player (Stardew, Animal Crossing, Minecraft) to Nasus and Kayle
on the strength of one macro-ish pick; the plain mean keeps them correctly on
Garen and Dr. Mundo but flattens the eclectic player. The upper-half mean
holds both.

The upper half is floored at two elements, which matters at exactly two
picks: taking one per dimension independently would invent a point no game
occupies. Four hand-made personas is a thin basis for a choice like this -
revisit it against real sessions.

The part that is not simple is **coverage**. Picking a game is a positive
signal; *not* picking one is ambiguous — it could mean dislike or could mean
never played. So a dimension is only readable from picks that actually take a
side on it. Five games all sitting at macro 0.5 say nothing about a player's
macro, however many of them there are, which is why the floor here is a
diversity floor and not a count (CLAUDE.md: a dimension the quiz could not read
is reported, never imputed).
"""

import statistics as st
from dataclasses import dataclass
from typing import Any

from r3m import db, scoring

DIMENSIONS = ("micro", "meso", "macro")

# How far from the middle a game has to sit before picking it says anything
# about that dimension.
INFORMATIVE = 0.25
# Two such picks per dimension, per the diversity floor.
NEEDED = 2


@dataclass(frozen=True)
class DimensionEstimate:
    value: float
    informative: int

    @property
    def read(self) -> bool:
        return self.informative >= NEEDED


@dataclass(frozen=True)
class Estimate:
    picked: list[dict[str, Any]]
    unknown: list[str]
    dimensions: dict[str, DimensionEstimate]

    @property
    def point(self) -> tuple[float, float, float]:
        return tuple(self.dimensions[d].value for d in DIMENSIONS)  # type: ignore[return-value]

    @property
    def unread(self) -> list[str]:
        return [d for d in DIMENSIONS if not self.dimensions[d].read]


def estimate(game_ids: list[str], rows: list[dict[str, Any]] | None = None) -> Estimate:
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    by_id = {r["game_id"]: r for r in rows}

    picked = [by_id[g] for g in game_ids if g in by_id]
    unknown = [g for g in game_ids if g not in by_id]
    if not picked:
        raise ValueError("none of those games are in the bank")

    dims = {}
    for d in DIMENSIONS:
        values = [p[d] for p in picked]
        # At least two picks in the upper half. With exactly two picks a
        # plain upper half is one element *per dimension independently*, so
        # osu! + Factorio would give (1.00, 0.12, 0.92): maximum micro from one
        # and maximum macro from the other, a player neither game describes and
        # no game occupies. Taking two collapses that case to the plain mean.
        keep = max(2, len(values) // 2)
        upper = sorted(values)[-keep:]
        dims[d] = DimensionEstimate(
            value=round(st.mean(upper), 2),
            informative=sum(1 for v in values if abs(v - 0.5) >= INFORMATIVE),
        )
    return Estimate(picked=picked, unknown=unknown, dimensions=dims)


def suggest_for(dimension: str, exclude: list[str],
                rows: list[dict[str, Any]] | None = None, n: int = 5) -> list[dict[str, Any]]:
    """Games that would actually settle a dimension the picks left open.

    Sorted by how far they sit from the middle on it — the ones that take the
    clearest side. This is the retry hook the unread-dimension decision calls
    for, not a general recommender.

    `exclude` must be everything already *served*, not just what was picked:
    offering someone a game they declined thirty seconds ago reads as the quiz
    not listening.
    """
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    candidates = [r for r in rows
                  if r["game_id"] not in exclude and r.get("in_bank", True)]
    return sorted(candidates, key=lambda r: -abs(r[dimension] - 0.5))[:n]


def champions_for(est: Estimate, n: int = 5) -> list[scoring.Match]:
    return scoring.neighbourhood(est.point, n=n)


# Three openers, chosen to be widely recognised and to sit far apart in the
# space: creative Minecraft is low on everything, Elden Ring is micro+macro,
# Among Us is meso. Everyone's first screens are familiar, and three answers
# already touch all three dimensions.
#
# Placeholder until reach data exists. The real rule weights candidates by how
# many people have played them as well as by information gain, and without
# Steam or Twitch numbers this is judgment standing in for measurement.
OPENER = ("minecraft-creative", "elden-ring", "among-us")

MAX_ITEMS = 10


def next_item(
    served: list[str], picked: list[str], rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The next game to ask about, or None when the quiz should stop.

    Fixed opener, then adaptive: serve whatever best settles the dimension
    currently least covered. Stops when every dimension is read or the bank
    budget is spent — a count alone would let three micro-ish picks end a quiz
    with meso and macro unmeasured.
    """
    by_id = {r["game_id"]: r for r in rows if r.get("in_bank", True)}
    if len(served) >= MAX_ITEMS:
        return None

    for game_id in OPENER:
        if game_id not in served and game_id in by_id:
            return by_id[game_id]

    if picked:
        est = estimate(picked, rows=rows)
        if not est.unread:
            return None
        # least covered first, so a dimension with nothing beats one with one
        target = min(est.unread, key=lambda d: est.dimensions[d].informative)
    else:
        target = "micro"

    candidates = [r for gid, r in by_id.items() if gid not in served]
    if not candidates:
        return None
    return max(candidates, key=lambda r: abs(r[target] - 0.5))
