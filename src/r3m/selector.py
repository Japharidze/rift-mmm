"""The card selector (docs/quiz-chain.md §4, "a card is a question").

Moved out of quiz.py unchanged on 2026-10-01 (a pure refactor). Serving uses it
only under quiz.SERVING = "selector", which is not switched on.
"""

import math
from typing import Any

from r3m.quiz import (
    DIMENSIONS, ENOUGH_RECOGNISED, MAX_ROUNDS, NEEDED, ROUND, Estimate, Reasons,
    _top, demand, estimate, servable_bank, spread_order,
)

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
    reasons: Reasons,
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
    reasons: Reasons,
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
