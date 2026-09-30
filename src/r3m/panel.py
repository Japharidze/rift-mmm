"""Panel comparison pass: the quiz's answer against what the player really plays.

The only external measure of match quality this project has
(docs/quiz-chain.md §8). For each stored quiz session that named a Riot
account: fetch the player's recent games and measure how the quiz point sits
relative to the champions they actually play.

**The headline (from panel round 2): each main on its own.** A player's mains
are their most-played champions, merged across roles. Each recommender --
the quiz point, the know-nothing centre, and popularity ("recommend what is
most played", from the match sample) -- orders every champion, and for each
we report where the *best* main lands, whether any main reaches the five the
quiz shows, where each main lands, and (for the two points) how far the
nearest main is. Chance for the first two depends on how many mains there
are, so it is printed beside them. CLAUDE.md requires a change to beat the
popularity baseline, not only the know-nothing point.

Why not the measures below as the headline: a mean over several mains of
different styles is smallest near the middle of the cloud, so the centre
wins it almost by construction -- the same failure as the centroid, softened.
The best main and the nearest main do not average anything.

**Secondary measures, in order of what they answer:**

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
# The headline's mains: a player's most-played champions, merged across roles.
MAINS = 5
# The quiz shows five champions.
HIT_AT = 5
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

    def rows_of(self, champion: str) -> list[tuple[tuple[str, str], Point]]:
        return [(k, p) for k, p in self._row.items() if k[0] == champion]

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


def top_mains(mains: Mains, known: set[str], n: int = MAINS) -> list[tuple[str, int]]:
    """(champion, games) for the player's n most-played labelled champions."""
    games: Counter = Counter()
    for champion, _, g in mains:
        if champion in known:
            games[champion] += g
    return games.most_common(n)


def order_from(point: Point, rows: list[dict[str, Any]]) -> list[str]:
    return [m.champion_id for m in scoring.neighbourhood(point, n=len(rows), rows=rows)]


def order_by_popularity(popularity: dict[str, int], rows: list[dict[str, Any]]) -> list[str]:
    champions = sorted({r["champion_id"] for r in rows})
    return sorted(champions, key=lambda c: -popularity.get(c, 0))


@dataclass(frozen=True)
class Ranking:
    """Where one recommender puts a player's mains. Ranks are percentiles of
    the recommender's order, 0 = first."""
    best: float
    hit: bool                       # a main among the first HIT_AT
    each: list[tuple[str, float]]
    nearest: float | None = None    # point recommenders only


def ranking(order: list[str], mains: list[tuple[str, int]],
            point: Point | None = None, main_points: MainPoints | None = None) -> Ranking:
    pos = {c: i / (len(order) - 1) for i, c in enumerate(order)}
    each = [(c, pos[c]) for c, _ in mains if c in pos]
    nearest = None
    if point is not None and main_points is not None:
        near = [math.dist(point, p) for c, _ in mains
                for (champion, _role), p in main_points.rows_of(c)]
        nearest = min(near) if near else None
    return Ranking(best=min(r for _, r in each), hit=any(c in order[:HIT_AT] for c, _ in each),
                   each=each, nearest=nearest)


def chance(n_champions: int, n_mains: int) -> tuple[float, float]:
    """(expected best-main percentile, P(a main in the first HIT_AT)) for a
    random order: more mains make both easier, so the bar moves with them."""
    best = (n_champions - n_mains) / (n_mains + 1) / max(1, n_champions - 1)
    if n_champions <= HIT_AT:
        return best, 1.0
    hit = 1 - math.comb(n_champions - n_mains, HIT_AT) / math.comb(n_champions, HIT_AT)
    return best, hit


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
    # Same (canonical) runs as the points above, so the variant differs from
    # the production matcher in the one column it swaps and nothing else.
    c_route = db.subtrait_values(conn, kind="champion", column="macro_routing")
    g_route = db.subtrait_values(conn, kind="game", column="macro_routing")

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
    mains: list[tuple[str, int]] = field(default_factory=list)   # the headline's
    quiz: Ranking | None = None
    centre: Ranking | None = None
    popular: Ranking | None = None                               # None: no match sample
    n_champions: int = 0


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
                  cache: dict[str, Any] | None = None, refetch: bool = False,
                  popularity: dict[str, int] | None = None) -> SessionCheck:
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
        points = MainPoints(v.champion_rows)
        placed = points.placed(out.mains)
        centre = roster_centre(v.champion_rows)
        known = {r["champion_id"] for r in v.champion_rows}
        mains = top_mains(out.mains, known)
        head: dict[str, Any] = {}
        if mains:
            head = dict(
                mains=mains,
                quiz=ranking(order_from(est.point, v.champion_rows), mains, est.point, points),
                centre=ranking(order_from(centre, v.champion_rows), mains, centre, points),
                popular=(ranking(order_by_popularity(popularity, v.champion_rows), mains)
                         if popularity else None),
                n_champions=len(known),
            )
        out.by_variant[v.name] = VariantResult(
            quiz_point=est.point,
            placed=placed,
            dist=mean_distance(est.point, placed),
            rank=mean_rank(est.point, placed, v.champion_rows),
            dist_ref=mean_distance(centre, placed),
            rank_ref=mean_rank(centre, placed, v.champion_rows),
            actual_point=centroid(placed)[0],
            **head,
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


def _headline(name: str, v: VariantResult) -> list[str]:
    if not v.mains or v.quiz is None:
        return [f"   [{name}] no labelled mains"]
    best, hit = chance(v.n_champions, len(v.mains))
    out = [f"   [{name}] mains: " + ", ".join(f"{c} x{g}" for c, g in v.mains),
           f"      {'':14} {'best':>5} {'hit':>4} {'nearest':>8}   each main"]
    for label, r in (("quiz point", v.quiz), ("know-nothing", v.centre), ("popularity", v.popular)):
        if r is None:
            out.append(f"      {label:14} (no match sample in this database)")
            continue
        out.append(f"      {label:14} {_pct(r.best):>5} {'yes' if r.hit else 'no':>4} {_num(r.nearest):>8}   "
                   + ", ".join(f"{c} {_pct(x)}" for c, x in r.each))
    out.append(f"      {'chance':14} {_pct(best):>5} {_pct(hit):>4}")
    return out


# Printed on every report: the two panel rounds differ in more than one thing.
ROUND_CAVEAT = [
    "CAVEAT: round 2 serves round 1's cards but Opus 5.5 labels (see build.game_runs) and new",
    "  evidence rules, so round-1-vs-round-2 differences mix label, rule and player changes.",
    "  Compare builds on the same answers instead: round 1's answers can be re-scored under",
    "  the new labels and rules, and round 2's raw answer log (quiz_session.events) under",
    "  any later build. The per-player numbers below already recompute every quiz point",
    "  under this database's served labels and the current rules, whatever built it.",
]


def outcome_lines(outcomes: dict[str, dict[str, Any]]) -> list[str]:
    """How every session ended, per round -- not only the ones with a Riot id: a
    player the quiz could not read never reaches the Riot-id comparison."""
    lines = ["OUTCOMES, all sessions (not only those with a Riot id):"]
    for rnd in sorted(outcomes):
        o = outcomes[rnd]
        ends = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(o["outcomes"].items()))
        unread = ", ".join(f"{k} unread: {v}" for k, v in sorted(o["unread"].items()))
        lines.append(f"  {rnd}: {o['sessions']} sessions, {o['riot_id']} with a Riot id; {ends}")
        if unread:
            lines.append(f"    results by dimensions left unread -- {unread}")
        if o["recovered"]:
            lines.append(f"    reached a result after first loving nothing: {o['recovered']}")
    return lines


# The steps of the quiz in the order a player meets them (migration 022).
STEPS = ([s for i in range(1, 6) for s in (f"round-{i}", f"loves-{i}")]
         + ["why", "fill", "deep", "compare", "nothing", "rating", "rated"])


def dropoff_lines(serving: str, d: dict[str, Any]) -> list[str]:
    """Completion and where people stop, for one serving mode. Its own block:
    partial sessions never enter the headline, which counts completed sessions
    with a Riot id only."""
    o = d["outcomes"]
    done = o.get("result", 0)
    abandoned = sum(d["abandoned_at"].values())
    lines = [f"DROP-OFF, {serving} (partial sessions are here only, never in the headline):",
             f"  started {d['started']}; reached a result {done}"
             + (f" ({100 * done / d['started']:.0f}% completion)" if d["started"] else "")
             + f"; loved nothing {o.get('loved_nothing', 0)}; no love for the gameplay "
             f"{o.get('no_gameplay_love', 0)}; abandoned {abandoned}; still going {d['still_going']}"]
    if abandoned:
        order = [s for s in STEPS if s in d["abandoned_at"]] + sorted(set(d["abandoned_at"]) - set(STEPS))
        lines.append("  abandoned at: " + ", ".join(f"{s} {d['abandoned_at'][s]}" for s in order))
    if done:
        lines.append(f"  rated the champions: {d['rated']} of {done}")
    return lines


def report(checks: list[SessionCheck], outcomes: dict[str, dict[str, Any]] | None = None,
           dropoff: dict[str, dict[str, Any]] | None = None) -> str:
    usable = [c for c in checks if not c.error and c.placed_games]
    n = len(usable)
    names = list(usable[0].by_variant) if usable else []
    lines = [f"Panel comparison pass: {len(checks)} session(s) with a Riot id, {n} usable."]
    lines += ROUND_CAVEAT
    if outcomes:
        lines += outcome_lines(outcomes)
    for serving, d in (dropoff or {}).items():
        lines += dropoff_lines(serving, d)
    if n < MIN_VERDICT_N:
        lines += [
            f"SANITY CHECK ONLY (n={n} < {MIN_VERDICT_N}). Per-player numbers show whether the",
            "pipeline works; no average and no variant difference is reported at this n.",
        ]
    lines += [
        f"HEADLINE, each main on its own (mains = the {MAINS} most-played champions):",
        "  best: where the best-placed main lands in the recommender's order (0% first).",
        f"  hit: a main among the first {HIT_AT}, the champions the quiz shows.",
        "  nearest: the point to the nearest main.  chance: a random order, for this many mains.",
        "  popularity is 'recommend what is most played'; a change must beat it (CLAUDE.md).",
        "SECONDARY:",
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
            lines += _headline(name, v)
        for name, v in c.by_variant.items():
            fit = fits[name].get(c.session_id)
            fit_s = "-" if fit is None else f"{fit[0]} of {fit[1]}"
            lines.append(f"   {name:14} quiz {_fmt(v.quiz_point)}  personal fit {fit_s}  "
                         f"dist {_num(v.dist)} (ref {_num(v.dist_ref)})  "
                         f"rank {_pct(v.rank)} (ref {_pct(v.rank_ref)})")

    if n >= MIN_VERDICT_N:
        lines.append("")
        for name in names:
            rs = [c.by_variant[name] for c in usable if c.by_variant[name].quiz]
            for label, get in (("quiz point", lambda v: v.quiz), ("know-nothing", lambda v: v.centre),
                               ("popularity", lambda v: v.popular)):
                got = [get(v) for v in rs if get(v) is not None]
                if got:
                    lines.append(f"{name:14} HEADLINE {label:12} best main {_pct(st.mean(g.best for g in got))}, "
                                 f"hit {_pct(st.mean(g.hit for g in got))} of {len(got)} players")
            ch = [chance(v.n_champions, len(v.mains)) for v in rs]
            if ch:
                lines.append(f"{name:14} HEADLINE {'chance':12} best main {_pct(st.mean(b for b, _ in ch))}, "
                             f"hit {_pct(st.mean(h for _, h in ch))}")
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
