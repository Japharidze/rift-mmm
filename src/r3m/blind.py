"""The blind ranking test (docs/blind-test.md): six champions, three from the
tester's own result and three from another tester's, shown identically and
ranked before the reveal.

Which three are "yoked": the top three of the completed session whose quiz
point is farthest from this tester's, recomputed from that stored point with
the labels serving now, so both halves come from the same labels. Any
champion in both sets is replaced by the other tester's next-ranked one.
"""

import math
import random
from functools import cache
from typing import Any

import yaml

from r3m import scoring
from r3m.config import ROOT

KIT_LINES_FILE = ROOT / "bank" / "kit_lines.yaml"
# The yoked session should be at least this far away; when none is, the
# farthest available is used and the distance is logged either way.
YOKE_MIN = 0.15
PER_SIDE = 3


@cache
def kit_lines() -> dict[str, str]:
    """champion_id -> the neutral one-line kit description. A champion without
    a line is never shown (an excluded line is removed from the file)."""
    return yaml.safe_load(KIT_LINES_FILE.read_text())


def _top(point: tuple[float, float, float], rows: list[dict[str, Any]],
         skip: set[str]) -> list[scoring.Match]:
    lines = kit_lines()
    out = [m for m in scoring.neighbourhood(point, n=len(rows), rows=rows)
           if m.champion_id in lines and m.champion_id not in skip]
    return out[:PER_SIDE]


def cards(point: tuple[float, float, float], sessions: list[tuple[int, list[float]]],
          rows: list[dict[str, Any]], seed: int | None = None) -> dict[str, Any] | None:
    """The six cards in display order, with what is logged about them, or None
    when no other session exists to yoke to."""
    if not sessions:
        return None
    yoked_id, yoked_point = max(sessions, key=lambda s: math.dist(point, s[1]))
    own = _top(point, rows, set())
    yoked = _top(tuple(yoked_point), rows, {m.champion_id for m in own})
    seed = random.randrange(2**31) if seed is None else seed
    shown = [(m, "own") for m in own] + [(m, "yoked") for m in yoked]
    random.Random(seed).shuffle(shown)
    distance = math.dist(point, yoked_point)
    return {
        "seed": seed,
        "yoked_session": yoked_id,
        "distance": round(distance, 3),
        "yoke_min_met": distance >= YOKE_MIN,
        # Each card's distance from this tester's own point, whichever side it
        # came from: the contrast d is later read against.
        "cards": [{"champion_id": m.champion_id, "name": m.name, "source": source,
                   "distance": round(math.dist(point, m.point), 3)} for m, source in shown],
    }
