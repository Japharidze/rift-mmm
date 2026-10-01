"""The reading: what the result says about the player (docs/quiz-chain.md §6.1).

Deterministic -- the sentences are bank/reading.yaml, approved by Sergi, and
these rules choose among them. No LLM, nothing drafted at runtime.

Every sentence carries the rule that chose it (`rule`), because the "not me"
tap logs it: a rejected sentence has to be traceable to the threshold, level
and games that produced it, or the rejection teaches nothing.

What is read:
- A dimension sentence only when the dimension is read and at least
  `moderate` from the middle; `strong` replaces moderate, never adds to it.
- The {games} are the player's own counting loves on the claimed side of the
  middle, the two with the largest share of that dimension -- the numbers the
  debug view shows. None qualifying means no sentence: it could not be personal.
- An unread dimension gets its unread line.
- A split sentence only with its parent dimension read and at least
  `split_parent`, and two or more deep-dive answers on the split, all agreeing.
- At most one champion reason: the dimension on which that champion fits the
  player better than the other champions shown, by `champion_margin`, where
  the player is at least moderate and the champion on the same side within
  `champion_gap`. Never a split: splits are observations, not reasons.
"""

from functools import cache
from typing import Any

import yaml

from r3m import deep_dives, quiz
from r3m.config import ROOT

READING_FILE = ROOT / "bank" / "reading.yaml"


@cache
def bank() -> dict[str, Any]:
    with READING_FILE.open() as fh:
        return yaml.safe_load(fh)


def version() -> str:
    return bank()["version"]


def _t(name: str) -> float:
    return float(bank()["thresholds"][name])


def _names(games: list[str]) -> str:
    return games[0] if len(games) == 1 else f"{', '.join(games[:-1])} and {games[-1]}"


def level(value: float) -> tuple[str, str] | None:
    """(side, strength) for a dimension value, or None near the middle."""
    dev = value - 0.5
    if abs(dev) < _t("moderate"):
        return None
    side = "high" if dev > 0 else "low"
    return side, "strong" if abs(dev) >= _t("strong") else "moderate"


def games_for(trace: list[dict[str, Any]], dimension: str, side: str,
              by_id: dict[str, dict[str, Any]], n: int = 2) -> list[str]:
    """The player's counting loves on `side` of the middle for `dimension`,
    largest share of that dimension first."""
    loves = [t for t in trace
             if t["kind"] == "love" and t.get("dimension") == dimension and t["weight"] > 0
             and (t["value"] > 0.5 if side == "high" else t["value"] < 0.5)]
    loves.sort(key=lambda t: -t["weight"])
    return [by_id[t["game"]]["name"] for t in loves[:n]]


def _sentence(sid: str, text: str, **rule: Any) -> dict[str, Any]:
    return {"id": sid, "text": text, "rule": rule}


def read_player(
    point: tuple[float, float, float],
    est: "quiz.Estimate",
    trace: list[dict[str, Any]],
    deep: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The reading's sentences, in a fixed order: dimensions, splits, unread.

    `point` is the final point (after deep dives and comparisons), which is
    what the champions were matched on; `est` and `trace` are the verdicts'
    estimate, which says what was read and which games moved each dimension.
    """
    by_id = {r["game_id"]: r for r in rows}
    out: list[dict[str, Any]] = []
    values = dict(zip(quiz.DIMENSIONS, point))

    for d in quiz.DIMENSIONS:
        if not est.dimensions[d].read:
            continue
        lv = level(values[d])
        if lv is None:
            continue
        side, strength = lv
        games = games_for(trace, d, side, by_id)
        if not games:
            continue
        key = f"{side}-{strength}"
        out.append(_sentence(f"{d}-{key}", bank()["dimensions"][d][key].format(games=_names(games)),
                             kind="dimension", dimension=d, level=key, value=round(values[d], 2),
                             threshold=_t(strength), games=games))

    for split, spec in bank()["splits"].items():
        parent = spec["parent"]
        if not est.dimensions[parent].read or values[parent] < _t("split_parent"):
            continue
        answers = []
        for a in deep:
            found = deep_dives._question(a.get("question", ""))
            if not found or a.get("option") is None or found[1]["axis"] != split:
                continue
            family, q = found
            option = next((o for o in q["options"] if o["id"] == a["option"]), None)
            if option:
                answers.append((option["sign"], deep_dives.deep_dives()[family]["name"]))
        signs = {s for s, _ in answers}
        if len(answers) < 2 or len(signs) != 1:
            continue
        sign = "+" if signs == {1} else "-"
        games = list(dict.fromkeys(name for _, name in answers))
        out.append(_sentence(f"{split}{sign}", spec[sign].format(games=_names(games)),
                             kind="split", split=split, direction=sign, answers=len(answers),
                             parent_value=round(values[parent], 2), games=games))

    for d in quiz.DIMENSIONS:
        if not est.dimensions[d].read:
            out.append(_sentence(f"{d}-unread", bank()["unread"][d], kind="unread", dimension=d))
    return out


def champion_reasons(
    point: tuple[float, float, float],
    est: "quiz.Estimate",
    trace: list[dict[str, Any]],
    shown: list[tuple[str, tuple[float, float, float]]],
    rows: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """For each champion shown (name, point), at most one reason it fits this
    player -- in the same order, an empty list where there is none.

    The reason is the dimension on which this champion fits the player better
    than the others shown do: closer to the player than the next-best of them
    by at least `champion_margin`, as well as qualifying on its own (the
    player clearly read there, the champion on the same side within
    `champion_gap`). Largest margin wins. A reason every champion shares says
    something about the player, not about this match -- the reading already
    says it -- and a win inside label noise could not mean anything to "not me".
    Standing out on nothing means no reason: an absent reason beats a
    manufactured one.
    """
    by_id = {r["game_id"]: r for r in rows}
    out: list[list[dict[str, Any]]] = []
    for k, (name, champ) in enumerate(shown):
        best = None
        for i, d in enumerate(quiz.DIMENSIONS):
            if not est.dimensions[d].read:
                continue
            lv = level(point[i])
            if lv is None:
                continue
            side, _ = lv
            same_side = champ[i] > 0.5 if side == "high" else champ[i] < 0.5
            mine = abs(champ[i] - point[i])
            if not same_side or mine > _t("champion_gap"):
                continue
            others = [abs(o[i] - point[i]) for j, (_, o) in enumerate(shown) if j != k]
            margin = (min(others) - mine) if others else 0.0
            if margin < _t("champion_margin"):
                continue
            games = games_for(trace, d, side, by_id)
            if games and (best is None or margin > best[0]):
                best = (margin, i, d, side, games)
        if best is None:
            out.append([])
            continue
        margin, i, d, side, games = best
        out.append([_sentence(f"champ-{d}-{side}",
                              bank()["champions"][d][side].format(champion=name, games=_names(games)),
                              kind="champion", dimension=d, side=side, value=round(point[i], 2),
                              champion_value=round(champ[i], 2), margin=round(margin, 3), games=games)])
    return out
