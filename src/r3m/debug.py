"""The developer view behind ?debug=1: how a result was reached.

Moved out of quiz.py unchanged on 2026-10-01 (a pure refactor).
"""

from typing import Any

from r3m import scoring
from r3m.deep_dives import DEEP_DIVE_SIZE, SPLITS, _question, apply_deep_dives, deep_dives, settle
from r3m.quiz import (
    CONFIDENT_LOVES, CONFIDENT_RECOGNISED, CONFIDENT_UNCERTAINTY, DIMENSIONS, Reasons,
    apply_comparisons, confidence, counting_loves, estimate, point_uncertainty, uncertainty,
)

# Debug view (?debug=1): how a result was reached. Never shown to players.
# ---------------------------------------------------------------------------

def debug_view(
    loved: list[str],
    disliked: list[str],
    reasons: Reasons,
    deep: list[dict[str, Any]],
    comparisons: list[dict[str, str]],
    rows: list[dict[str, Any]],
    champions: list[dict[str, Any]],
    n_champions: int = 10,
    recognised: int | None = None,
) -> dict[str, Any]:
    """Which games pushed which dimension, what each follow-up moved, and why
    each champion ranks where it does -- to judge a "partly" by component.
    Recomputed on the same functions the result uses, never re-derived."""
    by_id = {r["game_id"]: r for r in rows}
    trace: list[dict[str, Any]] = []
    est = estimate(loved, disliked, rows=rows, reasons=reasons, trace=trace)
    r2 = lambda x: round(x, 3)

    # Evidence: each game's share of each dimension's total weight.
    weight = {d: sum(t["weight"] for t in trace if t.get("dimension") == d) for d in DIMENSIONS}
    games: dict[str, dict[str, Any]] = {}
    for t in trace:
        g = games.setdefault(t["game"], {"game": t["game"], "name": by_id[t["game"]]["name"],
                                         "kind": t["kind"], "reason": t.get("reason"),
                                         "love_weight": t.get("love_weight"),
                                         "explained": t.get("explained", False), "dims": {}})
        if "dimension" in t:
            d = t["dimension"]
            g["dims"][d] = {"votes": r2(t["value"]), "share": r2(t["weight"] / weight[d]) if weight[d] else 0}

    # Follow-ups, in the order they apply.
    after_deep = apply_deep_dives(est, deep)
    dives = []
    for a in deep:
        found = _question(a.get("question", ""))
        if not found:
            continue
        _, q = found
        opt = next((o for o in q["options"] if o["id"] == a.get("option")), None)
        dives.append({"question": q["text"], "answer": opt["text"] if opt else None, "axis": q["axis"],
                      "move": (None if opt is None or q["axis"] in SPLITS
                               else r2(opt["sign"] * DEEP_DIVE_SIZE[q["size"]])),
                      "logged_only": q["axis"] in SPLITS})
    steps, prev = [], after_deep.point
    for k in range(1, len(comparisons) + 1):
        now = apply_comparisons(after_deep, comparisons[:k], rows).point
        c = comparisons[k - 1]
        steps.append({"winner": by_id.get(c["winner"], {}).get("name", c["winner"]),
                      "loser": by_id.get(c["loser"], {}).get("name", c["loser"]),
                      "dimension": c.get("dimension"),
                      "move": [r2(b - a) for a, b in zip(prev, now)]})
        prev = now
    final = settle(est, deep, comparisons, rows).point

    ranked = scoring.neighbourhood(final, n=n_champions, rows=champions)
    recognised = recognised if recognised is not None else len(loved) + len(disliked)
    loves = counting_loves(est, reasons)
    return {
        "uncertainty": {"per_dimension": uncertainty(est), "point": point_uncertainty(est),
                        "confident_below": CONFIDENT_UNCERTAINTY, "recognised": recognised,
                        "counting_loves": loves,
                        "floor": {"recognised": CONFIDENT_RECOGNISED, "loves": CONFIDENT_LOVES}},
        "points": {"verdicts": list(est.point), "after_deep_dives": list(after_deep.point),
                   "final": list(final)},
        "read": {d: {"informative": est.dimensions[d].informative, "read": est.dimensions[d].read}
                 for d in DIMENSIONS},
        "evidence": sorted(games.values(), key=lambda g: (g["kind"], g["name"])),
        "deep_dives": dives,
        "comparisons": steps,
        "champions": [{"name": m.name, "role": m.role, "distance": r2(m.distance),
                       "confidence": confidence(m.distance, est, recognised, loves),
                       "by_distance_alone": m.confidence,
                       "gap": {d: r2(m.point[i] - final[i]) for i, d in enumerate(DIMENSIONS)}}
                      for m in ranked],
    }
