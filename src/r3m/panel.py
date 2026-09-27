"""Panel comparison pass: the quiz's answer against what the player really plays.

The only external measure of match quality this project has
(docs/quiz-chain.md §8). For each stored quiz session that named a Riot
account: fetch the player's recent games, place their champions in MMM space,
and ask whether the quiz point sits nearer that than knowing nothing would.

Three rules keep it from misleading:

- **A baseline beside every number.** The distance from the quiz point to the
  player's mains means little alone. The "know-nothing" answer is the centroid
  of every champion x role; if the quiz does not beat it, the quiz added
  nothing, however small its own distance looks.
- **No verdict below MIN_VERDICT_N.** Round 1 left three Riot ids. Per-player
  numbers always print, because that is how the pipeline gets checked; a
  comparison between matcher variants is never stated as a winner below the
  floor, and the report says so first. Choosing a variant on three players fits
  the model to three friends.
- **Dry run by default.** Writing actual_point back is a separate flag: the
  configured database may be production.

Mains come from ranked, normal and quickplay queues. ARAM is excluded: the
champion is random and there is no position, so it says nothing about choice.
"""

import math
import statistics as st
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from r3m import db, quiz, scoring

# The panel is EUNE only (migration 012). eun1 routes to the `europe` regional
# host, which serves account-v1 and match-v5 for EUW accounts too.
PLATFORM = "eun1"
# Ranked solo, ranked flex, normal draft, quickplay, swiftplay. Asked per queue
# because the match-ids endpoint filters on one queue at a time.
QUEUES = (420, 440, 400, 490, 480)
MAX_MATCHES = 40
# Fewer labelled games than this and the centroid is reported but flagged: one
# tester in round 1 said outright "low amount of games".
THIN = 10
# Sessions needed before a variant comparison is reported as a result. A floor,
# not a power calculation: replace it with one once round 2 shows how much the
# per-player distance actually varies.
MIN_VERDICT_N = 30
# Round 1 asked for "Name#TAG" and two of three answers came without a tag.
# Accounts migrated to Riot ids got their region as the default tag, so those
# are tried in order and the report marks the tag as guessed.
DEFAULT_TAGS = ("EUNE", "EUW")
POSITION = {"TOP": "top", "JUNGLE": "jungle", "MIDDLE": "mid",
            "BOTTOM": "bot", "UTILITY": "support"}

Point = tuple[float, float, float]


def _pt(row: dict[str, Any]) -> Point:
    return (row["micro"], row["meso"], row["macro"])


def riot_id_candidates(raw: str) -> list[tuple[str, str, bool]]:
    """(game name, tag, whether the tag is a guess) to try, in order.

    Whitespace around '#' is dropped: round 1 stored "JohnRod #warud".
    """
    raw = raw.strip()
    if "#" in raw:
        name, tag = raw.split("#", 1)
        return [(name.strip(), tag.strip(), False)]
    return [(raw, tag, True) for tag in DEFAULT_TAGS]


def played(api: Any, puuid: str, max_matches: int = MAX_MATCHES) -> Counter:
    """Games per (champion_id, role) across the player's recent matches."""
    ids: set[str] = set()
    for queue in QUEUES:
        ids.update(api.match_ids(puuid, count=max_matches, queue=queue))
    # Match ids are PLATFORM_<sequence>; a higher sequence is a later game.
    recent = sorted(ids, key=lambda m: int(m.rsplit("_", 1)[-1]), reverse=True)
    counts: Counter = Counter()
    for match_id in recent[:max_matches]:
        info = api.match(match_id).get("info", {})
        me = next((p for p in info.get("participants", []) if p.get("puuid") == puuid), None)
        role = POSITION.get((me or {}).get("teamPosition", ""))
        if me and role:
            counts[(me["championName"], role)] += 1
    return counts


def centroid(counts: Counter, rows: list[dict[str, Any]]) -> tuple[Point | None, int]:
    """Games-weighted mean point of what was played, and how many games it used.

    A champion played in a role it has no label for (below the 30% threshold,
    so no champion x role row) falls back to the mean of its labelled rows; a
    champion with no label at all is left out, and the count says so.
    """
    by_row = {(r["champion_id"], r["role"]): _pt(r) for r in rows}
    by_champion: dict[str, list[Point]] = {}
    for r in rows:
        by_champion.setdefault(r["champion_id"], []).append(_pt(r))
    total, used = [0.0, 0.0, 0.0], 0
    for (champion, role), games in counts.items():
        p = by_row.get((champion, role))
        if p is None and champion in by_champion:
            pts = by_champion[champion]
            p = tuple(sum(x[i] for x in pts) / len(pts) for i in range(3))
        if p is None:
            continue
        for i in range(3):
            total[i] += p[i] * games
        used += games
    if not used:
        return None, 0
    return (total[0] / used, total[1] / used, total[2] / used), used


@dataclass(frozen=True)
class Variant:
    """A way of placing champions and games in the space, for comparison."""
    name: str
    champion_rows: list[dict[str, Any]]
    game_rows: list[dict[str, Any]]


def variants(conn: Any) -> list[Variant]:
    """The production matcher, and macro read through routing alone.

    The second exists to be *tested*, not adopted: docs/quiz-chain.md §2 records
    routing at +0.61 against the anchors versus +0.49 for the aggregate, and
    shipping it needs the Attribution sentence written down first.
    """
    champions = db.champion_points(conn)
    games = db.game_points(conn)
    c_route = db.subtrait_values(conn, kind="champion", column="macro_routing",
                                 prompt_version=champions[0]["prompt_version"])
    g_route = db.subtrait_values(conn, kind="game", column="macro_routing",
                                 prompt_version=games[0]["prompt_version"])

    def swap(rows: list[dict[str, Any]], key: Callable, values: dict) -> list[dict[str, Any]]:
        return [{**r, "macro": values.get(key(r), r["macro"])} for r in rows]

    return [
        Variant("current", champions, games),
        Variant("macro-routing",
                swap(champions, lambda r: (r["champion_id"], r["role"]), c_route),
                swap(games, lambda r: r["game_id"], g_route)),
    ]


@dataclass
class VariantResult:
    quiz_point: Point
    actual_point: Point | None
    d_quiz: float | None
    d_baseline: float | None
    main_rank: int | None


@dataclass
class SessionCheck:
    session_id: int
    riot_id: str
    resolved: str | None = None
    tag_guessed: bool = False
    error: str | None = None
    matches: int = 0
    labelled_games: int = 0
    mains: list[tuple[str, str, int]] = field(default_factory=list)
    recommended: list[str] = field(default_factory=list)
    stored_point: Point | None = None
    by_variant: dict[str, VariantResult] = field(default_factory=dict)

    @property
    def thin(self) -> bool:
        return self.labelled_games < THIN


def _roster_centroid(rows: list[dict[str, Any]]) -> Point:
    pts = [_pt(r) for r in rows]
    return tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))  # type: ignore[return-value]


def check_session(api: Any, session: dict[str, Any], variant_list: list[Variant]) -> SessionCheck:
    out = SessionCheck(session_id=session["id"], riot_id=session["riot_id"],
                       stored_point=tuple(session["point"]),
                       recommended=[c["name"] for c in session.get("champions", [])])
    puuid = None
    for name, tag, guessed in riot_id_candidates(session["riot_id"]):
        try:
            puuid = api.account_by_riot_id(name, tag)["puuid"]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                continue
            raise
        out.resolved, out.tag_guessed = f"{name}#{tag}", guessed
        break
    if puuid is None:
        tried = ", ".join(f"{n}#{t}" for n, t, _ in riot_id_candidates(session["riot_id"]))
        out.error = f"no account found (tried {tried})"
        return out

    counts = played(api, puuid)
    out.matches = sum(counts.values())
    out.mains = [(c, r, n) for (c, r), n in counts.most_common(5)]
    top_main = counts.most_common(1)[0][0][0] if counts else None

    for v in variant_list:
        actual, used = centroid(counts, v.champion_rows)
        try:
            est = quiz.estimate(session["loved"], session["disliked"], rows=v.game_rows)
        except ValueError as exc:  # no loved game has a label any more
            out.error = f"cannot recompute the quiz point: {exc}"
            return out
        if session.get("comparisons"):
            est = quiz.apply_comparisons(est, session["comparisons"], v.game_rows)
        point = est.point
        ranked = scoring.neighbourhood(point, n=len(v.champion_rows), rows=v.champion_rows)
        rank = next((i + 1 for i, m in enumerate(ranked) if m.champion_id == top_main), None)
        out.by_variant[v.name] = VariantResult(
            quiz_point=point,
            actual_point=actual,
            d_quiz=math.dist(point, actual) if actual else None,
            d_baseline=math.dist(_roster_centroid(v.champion_rows), actual) if actual else None,
            main_rank=rank,
        )
        out.labelled_games = max(out.labelled_games, used)
    return out


def _fmt(p: Point | None) -> str:
    return "-" if p is None else "/".join(f"{x:.2f}" for x in p)


def report(checks: list[SessionCheck], roster_size: int) -> str:
    usable = [c for c in checks if not c.error and c.labelled_games]
    n = len(usable)
    lines = [f"Panel comparison pass: {len(checks)} session(s) with a Riot id, {n} usable."]
    if n < MIN_VERDICT_N:
        lines += [
            f"SANITY CHECK ONLY (n={n} < {MIN_VERDICT_N}). The numbers below show whether",
            "the pipeline works end to end. They do not rank matcher variants: at this n",
            "any difference is noise, and choosing on it fits the model to these players.",
        ]
    lines.append("d(quiz) = quiz point to the centroid of the player's mains; "
                 "d(know-nothing) = the roster centroid to the same. Lower is closer.")
    for c in checks:
        lines.append("")
        head = f"#{c.session_id} {c.riot_id!r}"
        if c.error:
            lines.append(f"{head}: {c.error}")
            continue
        guess = " (tag guessed)" if c.tag_guessed else ""
        thin = "  THIN: too few games to trust the centroid" if c.thin else ""
        lines.append(f"{head} -> {c.resolved}{guess}: {c.matches} matches, "
                     f"{c.labelled_games} placed{thin}")
        lines.append("   mains: " + (", ".join(f"{ch} {r} x{k}" for ch, r, k in c.mains) or "none"))
        lines.append(f"   stored quiz point {_fmt(c.stored_point)}; recommended then: "
                     + (", ".join(c.recommended) or "-"))
        for name, v in c.by_variant.items():
            d = "-" if v.d_quiz is None else f"{v.d_quiz:.3f}"
            b = "-" if v.d_baseline is None else f"{v.d_baseline:.3f}"
            rank = "-" if v.main_rank is None else f"#{v.main_rank} of {roster_size}"
            lines.append(f"   {name:14} quiz {_fmt(v.quiz_point)}  mains {_fmt(v.actual_point)}  "
                         f"d(quiz) {d}  d(know-nothing) {b}  top main ranks {rank}")

    if n >= MIN_VERDICT_N:
        lines.append("")
        names = list(usable[0].by_variant)
        for name in names:
            ds = [c.by_variant[name].d_quiz for c in usable if c.by_variant[name].d_quiz is not None]
            bs = [c.by_variant[name].d_baseline for c in usable if c.by_variant[name].d_baseline is not None]
            lines.append(f"{name:14} mean d(quiz) {st.mean(ds):.3f}  mean d(know-nothing) {st.mean(bs):.3f}")
        if len(names) > 1:
            diffs = [c.by_variant[names[1]].d_quiz - c.by_variant[names[0]].d_quiz for c in usable]
            se = st.stdev(diffs) / math.sqrt(len(diffs))
            lines.append(f"{names[1]} minus {names[0]}: {st.mean(diffs):+.3f} "
                         f"(2 SE = {2 * se:.3f}; a difference inside 2 SE is not a result)")
    return "\n".join(lines)
