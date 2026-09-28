"""Panel comparison pass: the quiz's answer against what the player really plays.

The only external measure of match quality this project has
(docs/quiz-chain.md §8). For each stored quiz session that named a Riot
account: fetch the player's recent games and measure how the quiz point sits
relative to the champions they actually play.

**Three measures, in order of what they answer:**

1. **Personal fit** -- is *your* quiz point nearer your mains than the other
   players' quiz points are? This is the question the panel exists to answer
   ("is this about you?"), and it needs no baseline: other players are the
   baseline. Own-closest happens by chance 1 time in n.
2. **Distance to each main**, games-weighted, and **where your mains rank**
   among all champions ordered by distance from the quiz point (0% = nearest,
   50% = chance).
3. **Know-nothing**, the centroid of every champion x role, as a reference
   only. It is the point nearest on average to *any* champion, so it is a high
   bar, not a null result.

The first version compared the quiz point with the *centroid* of a player's
mains. That was wrong: averaging five or more champions lands near the middle
of the space, where the know-nothing point sits, so the baseline won by
construction (2026-09-28, three players, all three "lost"). Centroids are still
stored (actual_point, 011) but never reported as a measure.

**No verdict below MIN_VERDICT_N.** Per-player numbers always print; averages
across players and variant differences print only past the floor, and the
report opens by saying so. Choosing on three players fits the model to three
friends.

**Dry run by default.** Writing back is `--write`: the configured database may
be production.

Mains come from ranked, normal and quickplay queues. ARAM is excluded: the
champion is random and there is no position, so it says nothing about choice.
Fetched mains are kept in data/panel-mains.json as well as (with --write) on
the session: development keys expire every 24 hours, and re-fetching costs
~45 Riot calls per player.
"""

import json
import math
import statistics as st
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from r3m import db, quiz, scoring
from r3m.config import DATA_DIR

# The panel is EUNE only (migration 012). eun1 routes to the `europe` regional
# host, which serves account-v1 and match-v5 for EUW accounts too.
PLATFORM = "eun1"
# Ranked solo, ranked flex, normal draft, quickplay, swiftplay. Asked per queue
# because the match-ids endpoint filters on one queue at a time.
QUEUES = (420, 440, 400, 490, 480)
MAX_MATCHES = 40
# Fewer placed games than this and the numbers are flagged: one tester in
# round 1 said outright "low amount of games".
THIN = 10
# Sessions needed before averages or variant differences are reported. A floor,
# not a power calculation: replace it with one once round 2 shows how much the
# per-player measures actually vary.
MIN_VERDICT_N = 30
# Round 1 asked for "Name#TAG" and two of three answers came without a tag.
# Accounts migrated to Riot ids got their region as the default tag, so those
# are tried in order and the report marks the tag as guessed.
DEFAULT_TAGS = ("EUNE", "EUW")
POSITION = {"TOP": "top", "JUNGLE": "jungle", "MIDDLE": "mid",
            "BOTTOM": "bot", "UTILITY": "support"}
CACHE = DATA_DIR / "panel-mains.json"

Point = tuple[float, float, float]
Mains = list[tuple[str, str, int]]  # (champion_id, role, games), most-played first


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


def played(api: Any, puuid: str, max_matches: int = MAX_MATCHES) -> Mains:
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
    return [(c, r, n) for (c, r), n in counts.most_common()]


class MainPoints:
    """Where each (champion, role) a player played sits, under one variant.

    A champion played in a role it has no label for (below the 30% threshold,
    so no champion x role row) takes the mean of its labelled rows; a champion
    with no label at all has no point and is left out, and counts say so.
    """

    def __init__(self, rows: list[dict[str, Any]]):
        self._row = {(r["champion_id"], r["role"]): _pt(r) for r in rows}
        by_champion: dict[str, list[Point]] = {}
        for r in rows:
            by_champion.setdefault(r["champion_id"], []).append(_pt(r))
        self._champion = {c: tuple(st.mean(p[i] for p in ps) for i in range(3))
                          for c, ps in by_champion.items()}

    def get(self, champion: str, role: str) -> Point | None:
        return self._row.get((champion, role)) or self._champion.get(champion)  # type: ignore[return-value]

    def placed(self, mains: Mains) -> list[tuple[str, Point, int]]:
        out = []
        for champion, role, games in mains:
            p = self.get(champion, role)
            if p is not None:
                out.append((champion, p, games))
        return out


def mean_distance(point: Point, placed: list[tuple[str, Point, int]]) -> float | None:
    total = sum(g for _, _, g in placed)
    if not total:
        return None
    return sum(g * math.dist(point, p) for _, p, g in placed) / total


def mean_rank(point: Point, placed: list[tuple[str, Point, int]],
              rows: list[dict[str, Any]]) -> float | None:
    """Games-weighted percentile of each main among champions ordered by
    distance from the point: 0 = nearest of all, 0.5 = chance."""
    order = [m.champion_id for m in scoring.neighbourhood(point, n=len(rows), rows=rows)]
    total = sum(g for _, _, g in placed)
    if not total:
        return None
    return sum(g * order.index(c) / (len(order) - 1) for c, _, g in placed) / total


def centroid(placed: list[tuple[str, Point, int]]) -> tuple[Point | None, int]:
    """Games-weighted mean of the placed mains -- stored, never a measure."""
    total = sum(g for _, _, g in placed)
    if not total:
        return None, 0
    return tuple(sum(g * p[i] for _, p, g in placed) / total for i in range(3)), total  # type: ignore[return-value]


def roster_centre(rows: list[dict[str, Any]]) -> Point:
    pts = [_pt(r) for r in rows]
    return tuple(st.mean(p[i] for p in pts) for i in range(3))  # type: ignore[return-value]


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
    placed: list[tuple[str, Point, int]]
    dist: float | None            # quiz point to each main, games-weighted
    rank: float | None            # mains' percentile from the quiz point
    dist_ref: float | None        # the same two from the know-nothing point
    rank_ref: float | None
    actual_point: Point | None    # centroid, stored only


@dataclass
class SessionCheck:
    session_id: int
    riot_id: str
    resolved: str | None = None
    tag_guessed: bool = False
    source: str = "fetched"       # fetched | cache | stored
    error: str | None = None
    mains: Mains = field(default_factory=list)
    recommended: list[str] = field(default_factory=list)
    stored_point: Point | None = None
    by_variant: dict[str, VariantResult] = field(default_factory=dict)

    @property
    def games(self) -> int:
        return sum(g for _, _, g in self.mains)

    @property
    def placed_games(self) -> int:
        v = next(iter(self.by_variant.values()), None)
        return sum(g for _, _, g in v.placed) if v else 0

    @property
    def thin(self) -> bool:
        return self.placed_games < THIN


def load_cache(path: Path = CACHE) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict[str, Any], path: Path = CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, sort_keys=True))


def _resolve(api: Any, raw: str) -> tuple[str | None, str | None, bool]:
    for name, tag, guessed in riot_id_candidates(raw):
        try:
            return api.account_by_riot_id(name, tag)["puuid"], f"{name}#{tag}", guessed
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
    return None, None, False


def check_session(api: Any, session: dict[str, Any], variant_list: list[Variant], *,
                  cache: dict[str, Any] | None = None, refetch: bool = False) -> SessionCheck:
    out = SessionCheck(session_id=session["id"], riot_id=session["riot_id"],
                       stored_point=tuple(session["point"]),
                       recommended=[c["name"] for c in session.get("champions", [])])
    key = str(session["id"])
    cached = (cache or {}).get(key)
    if session.get("actual_mains") and not refetch:
        out.source, out.resolved = "stored", "(stored)"
        out.mains = [(m["champion_id"], m["role"], m["games"]) for m in session["actual_mains"]]
    elif cached and cached.get("riot_id") == session["riot_id"] and not refetch:
        out.source, out.resolved, out.tag_guessed = "cache", cached["resolved"], cached["tag_guessed"]
        out.mains = [tuple(m) for m in cached["mains"]]  # type: ignore[misc]
    else:
        puuid, out.resolved, out.tag_guessed = _resolve(api, session["riot_id"])
        if puuid is None:
            tried = ", ".join(f"{n}#{t}" for n, t, _ in riot_id_candidates(session["riot_id"]))
            out.error = f"no account found (tried {tried})"
            return out
        out.mains = played(api, puuid)
        if cache is not None:
            cache[key] = {"riot_id": session["riot_id"], "resolved": out.resolved,
                          "tag_guessed": out.tag_guessed, "mains": out.mains,
                          "fetched_at": datetime.now(UTC).isoformat(timespec="seconds")}

    for v in variant_list:
        try:
            est = quiz.estimate(session["loved"], session["disliked"], rows=v.game_rows)
        except ValueError as exc:  # no loved game has a label any more
            out.error = f"cannot recompute the quiz point: {exc}"
            return out
        if session.get("comparisons"):
            est = quiz.apply_comparisons(est, session["comparisons"], v.game_rows)
        placed = MainPoints(v.champion_rows).placed(out.mains)
        centre = roster_centre(v.champion_rows)
        out.by_variant[v.name] = VariantResult(
            quiz_point=est.point,
            placed=placed,
            dist=mean_distance(est.point, placed),
            rank=mean_rank(est.point, placed, v.champion_rows),
            dist_ref=mean_distance(centre, placed),
            rank_ref=mean_rank(centre, placed, v.champion_rows),
            actual_point=centroid(placed)[0],
        )
    return out


def personal_fit(checks: list[SessionCheck], variant: str) -> dict[int, tuple[int, int]]:
    """For each player: where their own quiz point ranks among every player's
    quiz point, by distance to *their* mains. (rank, n); rank 1 = own closest."""
    usable = [c for c in checks if not c.error and c.placed_games]
    out = {}
    for c in usable:
        placed = c.by_variant[variant].placed
        dists = sorted((mean_distance(o.by_variant[variant].quiz_point, placed), o.session_id)
                       for o in usable)
        out[c.session_id] = (1 + [sid for _, sid in dists].index(c.session_id), len(usable))
    return out


def _fmt(p: Point | None) -> str:
    return "-" if p is None else "/".join(f"{x:.2f}" for x in p)


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def _num(x: float | None) -> str:
    return "-" if x is None else f"{x:.3f}"


def report(checks: list[SessionCheck]) -> str:
    usable = [c for c in checks if not c.error and c.placed_games]
    n = len(usable)
    names = list(usable[0].by_variant) if usable else []
    lines = [f"Panel comparison pass: {len(checks)} session(s) with a Riot id, {n} usable."]
    if n < MIN_VERDICT_N:
        lines += [
            f"SANITY CHECK ONLY (n={n} < {MIN_VERDICT_N}). Per-player numbers show whether the",
            "pipeline works; no average and no variant difference is reported at this n.",
        ]
    lines += [
        "personal fit: your quiz point's rank among all players' quiz points, by distance",
        "  to your mains (1 = yours is closest; by chance 1 in n).",
        "dist: quiz point to each main, games-weighted.  rank: where your mains sit among",
        "  all champions ordered from the quiz point (0% nearest, 50% chance).",
        "ref: the same from the know-nothing point, the roster centre -- a high bar, not a null.",
    ]
    fits = {name: personal_fit(checks, name) for name in names}
    for c in checks:
        lines.append("")
        head = f"#{c.session_id} {c.riot_id!r}"
        if c.error:
            lines.append(f"{head}: {c.error}")
            continue
        guess = " (tag guessed)" if c.tag_guessed else ""
        thin = "  THIN: too few games to trust" if c.thin else ""
        lines.append(f"{head} -> {c.resolved}{guess} [{c.source}]: {c.games} games, "
                     f"{c.placed_games} placed{thin}")
        lines.append("   mains: " + (", ".join(f"{ch} {r} x{k}" for ch, r, k in c.mains[:6]) or "none"))
        lines.append("   recommended then: " + (", ".join(c.recommended) or "-"))
        for name, v in c.by_variant.items():
            fit = fits[name].get(c.session_id)
            fit_s = "-" if fit is None else f"{fit[0]} of {fit[1]}"
            lines.append(f"   {name:14} quiz {_fmt(v.quiz_point)}  personal fit {fit_s}  "
                         f"dist {_num(v.dist)} (ref {_num(v.dist_ref)})  "
                         f"rank {_pct(v.rank)} (ref {_pct(v.rank_ref)})")

    if n >= MIN_VERDICT_N:
        lines.append("")
        for name in names:
            own = sum(1 for r, _ in fits[name].values() if r == 1)
            fit_pct = st.mean((r - 1) / (m - 1) for r, m in fits[name].values())
            ranks = [c.by_variant[name].rank for c in usable if c.by_variant[name].rank is not None]
            lines.append(f"{name:14} own quiz point closest for {own} of {n} players "
                         f"(chance expects 1); mean personal-fit percentile {_pct(fit_pct)} "
                         f"(chance 50%); mean main rank {_pct(st.mean(ranks))} (chance 50%)")
        if len(names) > 1:
            diffs = [c.by_variant[names[1]].dist - c.by_variant[names[0]].dist for c in usable]
            se = st.stdev(diffs) / math.sqrt(len(diffs))
            lines.append(f"{names[1]} minus {names[0]}, dist: {st.mean(diffs):+.3f} "
                         f"(2 SE = {2 * se:.3f}; a difference inside 2 SE is not a result)")
    return "\n".join(lines)
