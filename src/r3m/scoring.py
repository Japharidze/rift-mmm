"""Scoring: an MMM point in, a style neighbourhood out.

Style first, role second (CLAUDE.md). The match is on the three coordinates
alone; the lane is reported with each result rather than filtered on, because
Gate 1 measured only moderate role information in the space -- enough to make
the lane label meaningful, not enough to pick it for the user.

Distance is plain Euclidean with equal weights, which is what CLAUDE.md fixes
for the pilot. Worth knowing what that means in practice: the three dimensions
do not vary equally across the roster (micro sd 0.18, macro 0.15, meso 0.13),
so equal weights give micro the largest say in who is "near". Standardising
first would equalise influence, but it would also stop the numbers meaning what
docs/sub-traits.md says they mean, so it is a decision rather than a tweak.
"""

import math
from dataclasses import dataclass
from typing import Any

from r3m import db

DIMENSIONS = ("micro", "meso", "macro")


# Set from the space, not picked. The median distance between a champion and
# its nearest neighbour is 0.051 across the 196 rows, so:
#
#   <= 0.10   within two champion-widths - as close as champions sit to each
#             other, so the match is real rather than nominal
#   <= 0.25   five champion-widths; a recognisable neighbourhood, not a twin
#   >  0.25   the nearest champion is far enough that the ranking is ordering
#             noise. Says more about the champion cloud than about the player.
#
# Gate 2 recorded that a 0.45 match must not be presented like a 0.04 one; this
# is where that becomes something the UI can act on. Measured 2026-09-23.
CLOSE = 0.10
FAIR = 0.25


@dataclass(frozen=True)
class Match:
    champion_id: str
    name: str
    role: str
    point: tuple[float, float, float]
    distance: float

    @property
    def confidence(self) -> str:
        if self.distance <= CLOSE:
            return "close"
        if self.distance <= FAIR:
            return "fair"
        return "distant"


def _point(row: dict[str, Any]) -> tuple[float, float, float]:
    return (row["micro"], row["meso"], row["macro"])


def neighbourhood(
    point: tuple[float, float, float],
    *,
    n: int = 5,
    rows: list[dict[str, Any]] | None = None,
) -> list[Match]:
    """The n nearest champions, best-matching role each.

    One entry per champion, not per champion x role: a two-role champion would
    otherwise take two of five slots with near-identical scores and crowd out
    a genuinely different suggestion.
    """
    if rows is None:
        with db.connect() as conn:
            rows = db.champion_points(conn)

    best: dict[str, Match] = {}
    for row in rows:
        p = _point(row)
        m = Match(
            champion_id=row["champion_id"],
            name=row["name"],
            role=row["role"],
            point=p,
            distance=math.dist(point, p),
        )
        seen = best.get(m.champion_id)
        if seen is None or m.distance < seen.distance:
            best[m.champion_id] = m

    return sorted(best.values(), key=lambda m: m.distance)[:n]
