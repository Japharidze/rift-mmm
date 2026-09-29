"""Synthetic players against the card selector (docs/quiz-chain.md §4).

The question: does a way of choosing cards find a player's true point when
recognition is noisier and more taste-shaped than the selector assumes?

**The players do not use the selector's model.** If a simulated player knew a
game with exactly the probability `quiz.recognition` predicts, and loved it
with exactly `quiz.verdict_odds`, the simulation would confirm its own
assumptions and every weighting would look fine. So both are independent here:

- *Recognition* starts from its own fame scale (different numbers for the
  renown tiers, a rank-based curve for Steam reach), then is perturbed heavily
  per player -- a breadth offset, so some know niche games and some miss the
  "universal" ones, and per-game noise on top -- and falls with distance from
  the player's own point: people mostly play games near their taste. That is
  the filter-bubble case the selector has to survive.
- *Verdicts* come from the distance between the true point and the game as
  this player perceives it (the label plus per-player noise), through
  different curves from `verdict_odds`, plus bias loves: nostalgia, friends,
  the childhood game, more likely for the games bank/bias.yaml rates high.

Every answer is a deterministic function of (player, game), so all policies
face the same players giving the same answers to the same cards (common
random numbers): a difference between policies is the policy's.

Only the recognition sweep is simulated -- the rounds the selector chooses.
Why-questions, the fill stage and comparisons come after and are not.

Surprising loves are counted, not rewarded (docs/quiz-chain.md §5): a policy
is scored on where it ends up, never on how far one answer moved the point.
"""

import hashlib
import math
import random
import statistics as st
from collections.abc import Callable
from dataclasses import dataclass, field
from multiprocessing import Pool
from typing import Any

from r3m import quiz, scoring

Point = tuple[float, float, float]

# -- the players' own world, deliberately not the selector's --------------------

# P(played it) for a typical player, before breadth, taste and noise. Wider
# apart than quiz.RENOWN_PRIOR (0.85 / 0.55 / 0.25) on purpose.
FAME = {"universal": 0.9, "wide": 0.45, "niche": 0.12}
# Steam reach by rank among the bank's Steam games, not log-linear like
# quiz.recognition_prior: the top of the list is known far more than the rest.
REACH_LOW, REACH_HIGH, REACH_CURVE = 0.08, 0.8, 2.0
UNRATED = 0.1
# Logit-scale perturbations. BREADTH is per player (how much they play at all);
# IDIOSYNCRASY is per player and game (this one just never came up).
BREADTH, IDIOSYNCRASY = 1.0, 1.2
# How strongly recognition falls with distance from the player's point, in
# logits per unit of distance, centred at TASTE_CENTRE so the average stays put.
TASTE, TASTE_CENTRE = 4.0, 0.35
# Per-player, per-game error in where a game sits, per dimension.
PERCEPTION = 0.08
# Verdict curves on the perceived distance.
LOVE_PEAK, LOVE_FLOOR, LOVE_WIDTH = 0.8, 0.05, 0.25
DISLIKE_MAX, DISLIKE_WIDTH = 0.55, 0.35
# A love for reasons no champion delivers, by bank/bias.yaml level.
BIAS_LOVE = {"low": 0.03, "medium": 0.10, "high": 0.25}
BIAS_UNRATED = 0.08
# Share of players whose point is drawn near a game rather than uniformly.
ANCHORED = 0.7
ANCHOR_SPREAD = 0.1


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _unit(*parts: Any) -> float:
    """A uniform number fixed by its inputs: the same player meets the same
    game the same way under every policy."""
    h = hashlib.blake2b(repr(parts).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**64


def _normal(*parts: Any) -> float:
    u1, u2 = max(_unit(*parts, 1), 1e-12), _unit(*parts, 2)
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def _pt(row: dict[str, Any]) -> Point:
    return (row["micro"], row["meso"], row["macro"])


def fame(rows: list[dict[str, Any]]) -> dict[str, float]:
    reached = sorted((r for r in rows if r.get("reach")), key=lambda r: r["reach"])
    pct = {r["game_id"]: i / max(1, len(reached) - 1) for i, r in enumerate(reached)}
    out = {}
    for r in rows:
        if r.get("renown") in FAME:
            out[r["game_id"]] = FAME[r["renown"]]
        elif r["game_id"] in pct:
            out[r["game_id"]] = REACH_LOW + (REACH_HIGH - REACH_LOW) * pct[r["game_id"]] ** REACH_CURVE
        else:
            out[r["game_id"]] = UNRATED
    return out


@dataclass(frozen=True)
class Player:
    seed: int
    true: Point
    breadth: float
    anchored: bool

    def recognises(self, row: dict[str, Any], base: float) -> bool:
        g = row["game_id"]
        logit = (_logit(base) + self.breadth + IDIOSYNCRASY * _normal(self.seed, g, "idio")
                 - TASTE * (math.dist(self.true, _pt(row)) - TASTE_CENTRE))
        return _unit(self.seed, g, "rec") < _sigmoid(logit)

    def verdict(self, row: dict[str, Any]) -> tuple[str, bool]:
        """(loved | disliked | fine, whether a love was for something else)."""
        g = row["game_id"]
        seen = tuple(min(1.0, max(0.0, row[d] + PERCEPTION * _normal(self.seed, g, d)))
                     for d in quiz.DIMENSIONS)
        dist = math.dist(self.true, seen)
        if _unit(self.seed, g, "love") < LOVE_FLOOR + LOVE_PEAK * math.exp(-(dist / LOVE_WIDTH) ** 2):
            return "loved", False
        if _unit(self.seed, g, "bias") < BIAS_LOVE.get(row.get("bias"), BIAS_UNRATED):
            return "loved", True
        if _unit(self.seed, g, "hate") < DISLIKE_MAX * (1 - math.exp(-(dist / DISLIKE_WIDTH) ** 2)):
            return "disliked", False
        return "fine", False


def players(n: int, rows: list[dict[str, Any]], seed: int = 0) -> list[Player]:
    rnd = random.Random(seed)
    deck = quiz.servable_bank(rows)
    out = []
    for i in range(n):
        anchored = rnd.random() < ANCHORED
        if anchored:
            centre = _pt(rnd.choice(deck))
            true = tuple(min(1.0, max(0.0, c + rnd.gauss(0, ANCHOR_SPREAD))) for c in centre)
        else:
            true = tuple(rnd.uniform(0.05, 0.95) for _ in range(3))
        out.append(Player(seed * 100_000 + i, true, rnd.gauss(0, BREADTH), anchored))  # type: ignore[arg-type]
    return out


# -- policies -------------------------------------------------------------------

Policy = Callable[..., list[dict[str, Any]] | None]


def _stop(index: int, played: list[str], loved: list[str], disliked: list[str],
          rows: list[dict[str, Any]]) -> bool:
    """next_round's stop rule, shared by the policies that have none of their own."""
    if index >= quiz.MAX_ROUNDS:
        return True
    if index > 0 and len(played) >= quiz.ENOUGH_RECOGNISED and loved:
        try:
            return not quiz.estimate(loved, disliked, rows=rows).unread
        except ValueError:
            return False
    return False


def policy(name: str, *, power: float = 1.0, explore: float = 1 / 3) -> Policy:
    def dealt(mode: str) -> Policy:
        def run(index, *, shown, played, loved, disliked, rows, champions, seed):
            quiz.SERVING = mode
            return quiz.next_round(index, played=played, loved=loved, disliked=disliked,
                                   reasons={}, rows=rows)
        return run

    def ranked(key: Callable[[dict[str, Any], float, random.Random], float]) -> Policy:
        def run(index, *, shown, played, loved, disliked, rows, champions, seed):
            if _stop(index, played, loved, disliked, rows):
                return None
            pool = [r for r in quiz.servable_bank(rows) if r["game_id"] not in set(shown)]
            by_id = {r["game_id"]: r for r in rows}
            k = quiz.breadth(shown, played, by_id)
            rnd = random.Random(f"{seed}-{index}")
            return sorted(pool, key=lambda r: -key(r, k, rnd))[:quiz.ROUND] or None
        return run

    def everything(index, *, shown, played, loved, disliked, rows, champions, seed):
        # A reference, not a policy: every deck card at once. The ceiling any
        # choice of cards can reach with this estimator and these players.
        return quiz.servable_bank(rows) if index == 0 else None

    def selector(index, *, shown, played, loved, disliked, rows, champions, seed):
        quiz.RECOGNITION_POWER, quiz.EXPLORE_SHARE = power, explore
        return quiz.select_round(index, shown=shown, played=played, loved=loved,
                                 disliked=disliked, reasons={}, rows=rows, champions=champions)

    return {
        "panel-round-1": dealt("panel-round-1"),
        "bank-dealt": dealt("bank"),
        "random": ranked(lambda r, k, rnd: rnd.random()),
        "recognition-only": ranked(lambda r, k, rnd: quiz.recognition(r, k)),
        "all-cards": everything,
        "selector": selector,
    }[name]


# -- one session, and the summary --------------------------------------------------

@dataclass
class Outcome:
    anchored: bool
    shown: int = 0
    recognised: int = 0
    loved: int = 0
    bias_loves: int = 0
    rounds: int = 0
    result: bool = False
    error: float | None = None        # estimate to true point, all three dimensions
    unread: int = 0
    overlap: int = 0                  # true top five recovered
    nearest: float = 0.0              # true point to its nearest champion, for context
    know_nothing: float = 0.0         # the roster centre's error, the panel pass's reference


def session(player: Player, run: Policy, rows: list[dict[str, Any]],
            champions: list[dict[str, Any]], base: dict[str, float],
            estimator: Callable[..., Any] | None = None) -> Outcome:
    out = Outcome(anchored=player.anchored)
    shown: list[str] = []
    played: list[str] = []
    loved: list[str] = []
    disliked: list[str] = []
    for index in range(quiz.MAX_ROUNDS):
        cards = run(index, shown=list(shown), played=list(played), loved=list(loved),
                    disliked=list(disliked), rows=rows, champions=champions, seed=player.seed)
        if not cards:
            break
        out.rounds += 1
        for r in cards:
            g = r["game_id"]
            shown.append(g)
            if not player.recognises(r, base[g]):
                continue
            played.append(g)
            v, bias = player.verdict(r)
            if v == "loved":
                loved.append(g)
                out.bias_loves += bias
            elif v == "disliked":
                disliked.append(g)
    out.shown, out.recognised, out.loved = len(shown), len(played), len(loved)
    truth = {m.champion_id for m in scoring.neighbourhood(player.true, n=5, rows=champions)}
    out.nearest = scoring.neighbourhood(player.true, n=1, rows=champions)[0].distance
    centre = tuple(st.mean(c[d] for c in champions) for d in quiz.DIMENSIONS)
    out.know_nothing = math.dist(centre, player.true)
    try:
        est = (estimator or quiz.estimate)(loved, disliked, rows=rows)
    except ValueError:
        return out
    out.result = True
    out.error = math.dist(est.point, player.true)
    out.unread = len(est.unread)
    out.overlap = len(truth & {m.champion_id for m in scoring.neighbourhood(est.point, n=5, rows=champions)})
    return out


@dataclass
class Summary:
    name: str
    n: int
    no_result: float
    error: float
    error_p90: float
    overlap: float
    unread: float
    shown: float
    recognised: float
    know_nothing: float = math.nan
    by_group: dict[str, float] = field(default_factory=dict)


def summarise(name: str, outcomes: list[Outcome]) -> Summary:
    done = [o for o in outcomes if o.result]
    errors = [o.error for o in done]
    groups = {
        "anchored": [o.error for o in done if o.anchored],
        "uniform": [o.error for o in done if not o.anchored],
        "no bias love": [o.error for o in done if not o.bias_loves],
        "bias love": [o.error for o in done if o.bias_loves],
    }
    return Summary(
        name=name, n=len(outcomes),
        no_result=1 - len(done) / len(outcomes),
        error=st.mean(errors) if errors else math.nan,
        error_p90=st.quantiles(errors, n=10)[8] if len(errors) > 1 else math.nan,
        overlap=st.mean(o.overlap for o in done) if done else math.nan,
        unread=st.mean(o.unread for o in done) if done else math.nan,
        shown=st.mean(o.shown for o in outcomes),
        recognised=st.mean(o.recognised for o in outcomes),
        know_nothing=st.mean(o.know_nothing for o in outcomes),
        by_group={k: st.mean(v) if v else math.nan for k, v in groups.items()},
    )


def _work(args: tuple) -> list[Outcome]:
    spec, chunk, rows, champions, base = args
    name, kw = spec
    kw = dict(kw)
    width = kw.pop("robust", None)
    run = policy(name, **kw)
    est = robust(width) if width else None
    return [session(p, run, rows, champions, base, est) for p in chunk]


def simulate(specs: list[tuple[str, dict[str, Any]]], rows: list[dict[str, Any]],
             champions: list[dict[str, Any]], n: int = 300, seed: int = 0,
             workers: int = 8) -> list[Summary]:
    people = players(n, rows, seed)
    base = fame(rows)
    chunks = [people[i::workers] for i in range(workers)]
    out = []
    with Pool(workers) as pool:
        for spec in specs:
            parts = pool.map(_work, [(spec, c, rows, champions, base) for c in chunks])
            label = spec[0] + "".join(f" {k}={v:.2g}" for k, v in spec[1].items())
            out.append(summarise(label, [o for part in parts for o in part]))
    return out


def report(summaries: list[Summary]) -> str:
    lines = [
        "error: estimate to true point (all three dimensions); p90 is the worst tenth.",
        "top5: of the true top five champions, how many the estimate recovers.",
        "none: sessions with nothing loved, so no result. unread: dimensions left open.",
        "",
        f"{'policy':34} {'error':>6} {'p90':>6} {'top5':>5} {'none':>5} {'unread':>6} "
        f"{'shown':>6} {'known':>6}   {'anchored':>8} {'uniform':>8} {'no-bias':>8} {'bias':>8}",
    ]
    for s in summaries:
        g = s.by_group
        lines.append(
            f"{s.name:34} {s.error:6.3f} {s.error_p90:6.3f} {s.overlap:5.2f} {100 * s.no_result:4.0f}% "
            f"{s.unread:6.2f} {s.shown:6.1f} {s.recognised:6.1f}   {g['anchored']:8.3f} "
            f"{g['uniform']:8.3f} {g['no bias love']:8.3f} {g['bias love']:8.3f}")
    if summaries:
        lines.append(f"{'know-nothing (roster centre)':34} {summaries[0].know_nothing:6.3f}")
    return "\n".join(lines)


# -- estimators under test ------------------------------------------------------------

def robust(width: float, iterations: int = 5) -> Callable[..., "quiz.Estimate"]:
    """Triangulation (docs/quiz-chain.md §5): trust patterns across games, not
    single games. Start from the served estimate, then re-weight each love by
    how well it agrees with the rest -- a Cauchy weight on its distance from the
    current point -- and re-estimate, a few times.

    Distance is taken only where the game presents demand, in proportion to
    its opportunity: osu! loved by a high-micro player is measured on micro and
    agrees, though in three dimensions it sits far from any generalist point.
    Measured on all three, every specialist love would read as an outlier.
    """
    def run(loved: list[str], disliked: list[str], rows: list[dict[str, Any]],
            reasons: dict[str, str] | None = None) -> quiz.Estimate:
        by_id = {r["game_id"]: r for r in rows}
        est = quiz.estimate(loved, disliked, rows=rows, reasons=reasons)
        for _ in range(iterations):
            scale = {}
            for g in loved:
                r = by_id.get(g)
                if r is None:
                    continue
                opp = {d: quiz.opportunity(r, d) for d in quiz.DIMENSIONS}
                total = sum(opp.values()) or 1.0
                gap = math.sqrt(sum(opp[d] / total * (r[d] - est.dimensions[d].value) ** 2
                                    for d in quiz.DIMENSIONS))
                scale[g] = 1 / (1 + (gap / width) ** 2)
            est = quiz.estimate(loved, disliked, rows=rows, reasons=reasons, scale=scale)
        return est
    return run
