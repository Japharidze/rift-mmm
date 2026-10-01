"""Deep dives: questions about how someone played a game they loved
(bank/deep_dives.yaml, docs/quiz-chain.md §3, §4).

Moved out of quiz.py unchanged on 2026-10-01 (a pure refactor).
"""

from functools import cache
from typing import Any

import yaml

from r3m.config import ROOT
from r3m.quiz import DIMENSIONS, DimensionEstimate, Estimate, Reasons, apply_comparisons

# Deep dives (docs/quiz-chain.md §3, §4): how someone played a game they loved.
# ---------------------------------------------------------------------------

DEEP_DIVES_FILE = ROOT / "bank" / "deep_dives.yaml"
# One answer's pull on its axis. Below scoring.CLOSE, so like a comparison no
# single answer relocates the point; the two options of a question pull the
# same size in opposite directions, so a random answerer does not drift.
DEEP_DIVE_SIZE = {"small": 0.04, "medium": 0.08}
# All deep-dive answers together move one dimension at most this far (scoring's
# CLOSE band) -- the principle already applied to comparisons: no single source
# relocates the point. Two macro answers in two families stacked to +0.16 in a
# test and lifted the point above every champion (2026-09-30, Sergi).
DEEP_DIVE_CAP = 0.10
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
    reasons: Reasons,
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
        given = reasons.get(g)
        given = {given} if isinstance(given, str) else set(given or ())
        if given and "gameplay" not in given:   # loved only for something else
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
    in its option's direction, and all of them together move one dimension at
    most DEEP_DIVE_CAP. Split answers and skips move nothing."""
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
    delta = {d: max(-DEEP_DIVE_CAP, min(DEEP_DIVE_CAP, v)) for d, v in delta.items()}
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
