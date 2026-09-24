"""What a player enjoys -> an MMM point -> champions.

The concept is taste, not exposure. CLAUDE.md: "a player's *taste* in games
they already know points toward champions worth trying", and docs/3m-model.md
bets that *preferences* transfer because MMM describes the person. An earlier
version of this module asked "have you played X", which nearly everyone answers
yes to for Minecraft and which says nothing about whether they enjoyed it.

So an answer is three-way, and each one means something different:

  loved        positive evidence: you enjoy that level of demand
  didn't stick negative evidence: you met that level and it did not hold you
  never played no evidence at all

Negative evidence is the part that was missing, and it earns its keep twice.
It is genuinely informative — bouncing off Dark Souls says something bouncing
off nothing does not — and it removes a hack. When "not picked" conflated
dislike with never-played, a plain mean was wrong (a low pick dragged as hard
as a high pick lifted), so the estimate used the mean of the upper half with a
floor, justified at length. With dislike stated outright, that ambiguity is
gone and a plain weighted mean is both simpler and more honest.

A disliked game contributes a *reflected* observation at half weight: bouncing
off osu! (micro 0.98) is weak evidence for preferring low micro, and bouncing
off Animal Crossing (micro 0.12) is weak evidence for preferring more. Half
weight because a person can dislike a game for reasons this model knows nothing
about — monetisation, art style, the friend who made them play it.
"""

from dataclasses import dataclass, field
from typing import Any

from r3m import db, scoring

DIMENSIONS = ("micro", "meso", "macro")

# How far from the middle a game sits before an answer about it says anything.
INFORMATIVE = 0.25
# Informative answers per dimension before it counts as read. A diversity
# floor, not a count: three micro-ish answers leave meso and macro unmeasured
# however many were served.
#
# Raised from 2 once the grid replaced the three-item opener. A 28-card grid
# hands over many more picks than a handful of single cards did, and at 2 a
# typical grid cleared every dimension outright -- which skipped the fill stage
# almost always, and called an axis read on two observations. Measured over
# random picks from the grid, the fill stage now runs for 84% of five-pick
# sessions and 32% of eight-pick ones, and someone who tapped twelve games has
# genuinely been read and skips it.
NEEDED = 3
# Dislike is real evidence, but noisier than delight.
DISLIKE_WEIGHT = 0.5


@dataclass(frozen=True)
class DimensionEstimate:
    value: float
    # Weighted: a loved game counts 1, a disliked one DISLIKE_WEIGHT.
    informative: float

    @property
    def read(self) -> bool:
        return self.informative >= NEEDED


@dataclass(frozen=True)
class Estimate:
    loved: list[dict[str, Any]] = field(default_factory=list)
    disliked: list[dict[str, Any]] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    dimensions: dict[str, DimensionEstimate] = field(default_factory=dict)

    @property
    def point(self) -> tuple[float, float, float]:
        return tuple(self.dimensions[d].value for d in DIMENSIONS)  # type: ignore[return-value]

    @property
    def unread(self) -> list[str]:
        return [d for d in DIMENSIONS if not self.dimensions[d].read]

    @property
    def answered(self) -> list[str]:
        return [g["game_id"] for g in (*self.loved, *self.disliked)]


def estimate(
    loved: list[str],
    disliked: list[str] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> Estimate:
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    by_id = {r["game_id"]: r for r in rows}
    disliked = disliked or []

    liked_rows = [by_id[g] for g in loved if g in by_id]
    disliked_rows = [by_id[g] for g in disliked if g in by_id]
    unknown = [g for g in (*loved, *disliked) if g not in by_id]

    if not liked_rows:
        # Without something enjoyed there is no positive anchor, and an
        # estimate built only from reflections of dislikes would be a guess
        # wearing a number.
        raise ValueError("need at least one game you enjoyed")

    dims = {}
    for d in DIMENSIONS:
        total = sum(r[d] for r in liked_rows)
        weight = float(len(liked_rows))
        for r in disliked_rows:
            total += DISLIKE_WEIGHT * (1.0 - r[d])
            weight += DISLIKE_WEIGHT
        # Weighted the same way the value is. A dislike contributing half an
        # observation to the number but a whole one to "we have read this"
        # was inconsistent, and it mattered: the grid's second pass makes
        # bouncing off cheap to tap, so a handful of dislikes could declare a
        # dimension read on evidence the estimate itself only half trusts.
        informative = sum(
            1.0 if r in liked_rows else DISLIKE_WEIGHT
            for r in (*liked_rows, *disliked_rows)
            if abs(r[d] - 0.5) >= INFORMATIVE
        )
        dims[d] = DimensionEstimate(value=round(total / weight, 2), informative=informative)

    return Estimate(loved=liked_rows, disliked=disliked_rows, unknown=unknown, dimensions=dims)


def suggest_for(dimension: str, exclude: list[str],
                rows: list[dict[str, Any]] | None = None, n: int = 5) -> list[dict[str, Any]]:
    """Games that would settle a dimension the answers left open.

    `exclude` must be everything already *served*, not just what was answered
    about: re-offering a game somebody just dismissed reads as not listening.
    """
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    candidates = [r for r in rows
                  if r["game_id"] not in exclude and r.get("in_bank", True)]
    return sorted(candidates, key=lambda r: -abs(r[dimension] - 0.5))[:n]


def champions_for(est: Estimate, n: int = 5) -> list[scoring.Match]:
    return scoring.neighbourhood(est.point, n=n)


# Three openers, widely recognised and far apart in the space: creative
# Minecraft is low on everything, Elden Ring is micro+macro, Among Us is meso.
# Placeholder until reach data exists — the real rule weights candidates by how
# many people have played them as well as by how much the answer would settle.
OPENER = ("minecraft-creative", "elden-ring", "among-us")

MAX_ITEMS = 10


def next_item(
    served: list[str],
    loved: list[str],
    disliked: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """The next game to ask about, or None when the quiz should stop."""
    by_id = {r["game_id"]: r for r in rows if r.get("in_bank", True)}
    if len(served) >= MAX_ITEMS:
        return None

    for game_id in OPENER:
        if game_id not in served and game_id in by_id:
            return by_id[game_id]

    target = "micro"
    if loved:
        est = estimate(loved, disliked, rows=rows)
        if not est.unread:
            return None
        target = min(est.unread, key=lambda d: est.dimensions[d].informative)

    candidates = [r for gid, r in by_id.items() if gid not in served]
    if not candidates:
        return None
    return max(candidates, key=lambda r: abs(r[target] - 0.5))


# What each dimension is called where a person can see it. The internal names
# are Surnex's and stay that way in the data; "meso 0.62" is meaningless to
# someone who has never read the model.
LABELS = {
    "micro": ("Execution", "aim, timing, and hitting things precisely"),
    "meso": ("Reading people", "predicting, baiting, and outguessing an opponent"),
    "macro": ("Planning", "where to be, what to build toward, when to commit"),
}

# Above this a dimension reads as "high", below its mirror as "low". Matches
# INFORMATIVE so the same answer that counts as evidence also counts as a
# trait worth naming.
STRONG = 0.5 + INFORMATIVE


def explain(est: Estimate, match: scoring.Match) -> str | None:
    """One sentence on why this champion, in the player's terms.

    Picks the dimension the player is most decided about *and* the champion
    agrees on — being sure about something the champion does not share is not
    a reason. Returns None when there is no such trait, because inventing a
    reason is worse than omitting one.
    """
    best, best_score = None, 0.0
    for i, d in enumerate(DIMENSIONS):
        mine, theirs = est.dimensions[d].value, match.point[i]
        decided = abs(mine - 0.5)
        if decided < INFORMATIVE:
            continue
        agreement = decided - abs(mine - theirs)
        if agreement > best_score:
            best, best_score = d, agreement
    if best is None:
        return None

    name, gloss = LABELS[best]
    high = est.dimensions[best].value >= 0.5
    return (
        f"You lean {'into' if high else 'away from'} {name.lower()} — {gloss}. "
        f"{match.name} {'does too' if high else 'asks little of it either'}."
    )


# ---------------------------------------------------------------------------
# Staged flow: grid -> fill -> specify (docs/quiz-flow.md)
# ---------------------------------------------------------------------------

# Cards in the opening grid. Larger than feels right from one-at-a-time
# thinking, where every served item costs a decision -- a grid is scanned, so
# an unrecognised card costs a glance. Showing more buys coverage of the space
# almost free, and at 28 of 43 the hand-curation problem mostly dissolves.
GRID = 28
# How much spread a card with cover art may give up to displace one without.
# High enough to only swap near-ties: a genuinely isolated corner of the space
# is still taken text-only rather than left uncovered.
ART_SLACK = 0.85
# Single cards after the grid. Zero to four, and often zero: this stage only
# runs for dimensions the grid left unread.
FILL_MAX = 4


def grid(rows: list[dict[str, Any]] | None = None, n: int = GRID) -> list[dict[str, Any]]:
    """The opening grid: a farthest-point traversal of the bank.

    Take the most extreme game, then repeatedly take whichever is furthest
    from everything already picked. Covers the poles by construction rather
    than by judgement, which is the half of the problem that is decidable --
    recognisability is the other half and needs reach data the bank does not
    carry yet.

    Extremes come first, so the *tail* is the middle of the space, which is
    where the mainstream lives. That is the right way round: the grid absorbs
    the obscure items, where a card costs a glance, and `fill_item` inherits
    the recognisable ones, where an item costs a decision.

    Cover art breaks the tie. Distance alone concentrated the art gap into the
    grid -- the poles are disproportionately the Nintendo, Blizzard and mobile
    titles Steam does not carry, so 12 of 28 cards came out text-only while the
    games it discarded mostly had covers. Where a card with art is nearly as
    far out as the best candidate, it is taken instead: the grid is the one
    screen that has to read as a deck, and a coverage difference that small is
    not worth half the screen looking unfinished.
    """
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    pool = [r for r in rows if r.get("in_bank", True)]
    if not pool:
        return []

    def gap(a: dict[str, Any], b: dict[str, Any]) -> float:
        return sum((a[d] - b[d]) ** 2 for d in DIMENSIONS) ** 0.5

    middle = {d: 0.5 for d in DIMENSIONS}
    picked = [max(pool, key=lambda r: gap(r, middle))]
    rest = [r for r in pool if r is not picked[0]]
    while rest and len(picked) < n:
        spread = {id(r): min(gap(r, p) for p in picked) for r in rest}
        best = max(rest, key=lambda r: spread[id(r)])
        nxt = best
        if not best.get("steam_appid"):
            withart = [r for r in rest
                       if r.get("steam_appid")
                       and spread[id(r)] >= ART_SLACK * spread[id(best)]]
            if withart:
                nxt = max(withart, key=lambda r: spread[id(r)])
        picked.append(nxt)
        rest.remove(nxt)
    return picked


def fill_item(
    served: list[str],
    loved: list[str],
    disliked: list[str],
    rows: list[dict[str, Any]],
    asked: int = 0,
) -> dict[str, Any] | None:
    """Stage 2: one more card, or None when there is nothing left to read.

    Unlike `next_item` there is no opener -- the grid was the opener -- and the
    budget counts only what this stage served, not the whole grid. Returns None
    the moment every dimension is read, so the common case is that this stage
    does not run at all.
    """
    if asked >= FILL_MAX or not loved:
        return None
    est = estimate(loved, disliked, rows=rows)
    if not est.unread:
        return None
    target = min(est.unread, key=lambda d: est.dimensions[d].informative)

    candidates = [r for r in rows
                  if r.get("in_bank", True) and r["game_id"] not in served]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: abs(r[target] - 0.5))
    # A card that says nothing about the open dimension is not worth a screen.
    return best if abs(best[target] - 0.5) >= INFORMATIVE else None


# A pair isolates a dimension when the two games are far apart on it and close
# on the other two: everything but the target is controlled, so the answer
# reads as an opinion about the target alone.
PAIR_SPLIT = 0.35
PAIR_MATCH = 0.15
# Comparisons offered after the result. Small: this sharpens an answer the user
# has already been shown, and a fourth screen of it stops being a refinement.
SHARPEN_MAX = 3
# How far to nudge a dimension when asking whether it changes the answer. Set
# by the space, not chosen: the median distance between a champion and its
# nearest neighbour is 0.051 and scoring.CLOSE is 0.10, so this is the
# smallest move that can reorder a list.
NUDGE = 0.05
# Fraction of the gap to the winner that one comparison pulls, before the cap.
# Deliberately small. Pairs are contrastive by construction, so the winner is
# always far from the current estimate -- at half the gap a single comparison
# saturated the cumulative cap, which made every answer move the same distance
# and turned the cap into the only parameter. At a fifth, one answer nudges by
# about NUDGE (enough to reorder the list, not to relocate it) and it takes
# roughly a full SHARPEN_MAX of agreeing answers to reach the ceiling.
COMPARISON_PULL = 0.2


def contrastive(a: dict[str, Any], b: dict[str, Any]) -> str | None:
    """The dimension this pair isolates, or None if it isolates nothing."""
    for d in DIMENSIONS:
        if abs(a[d] - b[d]) >= PAIR_SPLIT and all(
            abs(a[o] - b[o]) <= PAIR_MATCH for o in DIMENSIONS if o != d
        ):
            return d
    return None


def sensitivity(est: "Estimate", n: int = 5) -> dict[str, int]:
    """Per dimension, how many of the top n champions a nudge displaces.

    The question worth spending a user's attention on is not "which dimension
    am I least sure about" but "which uncertainty actually changes what I would
    tell you". Those are different axes, and only the second one is worth a
    screen.
    """
    base = {(m.champion_id, m.role) for m in champions_for(est, n=n)}
    out = {}
    for i, d in enumerate(DIMENSIONS):
        worst = 0
        for sign in (1, -1):
            point = list(est.point)
            point[i] = min(1.0, max(0.0, point[i] + sign * NUDGE))
            moved = {(m.champion_id, m.role)
                     for m in scoring.neighbourhood(tuple(point), n=n)}
            worst = max(worst, len(base - moved))
        out[d] = worst
    return out


def pair_for(
    est: "Estimate", dimension: str, used: list[str] | None = None
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """A contrastive pair on `dimension`, drawn from what the player recognised.

    Drawn from answered games rather than the bank because a comparison can
    fail in a way a verdict cannot: serve two games the player has not played
    and the screen bought nothing, whereas "never played" is a valid answer to
    a verdict. Every game here carries a verdict, so both cards are known.

    Recognised, not loved. Restricting the pool to the loved set looked right
    -- "you liked both, which more" is the cleanest version of the question --
    but the grid broke it. A second pass that asks what you bounced off makes
    dislikes cheap to tap, and people mark many; those count toward a dimension
    being read, which closes the fill stage, while a loved-only pool stays tiny
    and closes this one too. Measured at three loved and eight disliked: the
    fill stage fired 6% of the time and a pair existed 24%. Both stages
    vanished for anyone who used the second pass the way it invites.

    Re-using answered games is not double-counting, provided the answer updates
    the point relatively (`apply_comparisons`) rather than landing as a fresh
    absolute observation. "Which would you go back to" is information a
    three-way verdict had no way to express, whichever verdicts those two games
    got.
    """
    used = used or []
    pool = [*est.loved, *est.disliked]
    best, widest = None, 0.0
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            if a["game_id"] in used or b["game_id"] in used:
                continue
            if contrastive(a, b) != dimension:
                continue
            split = abs(a[dimension] - b[dimension])
            if split > widest:
                best, widest = (a, b), split
    return best


def sharpen(
    est: "Estimate", used: list[str] | None = None
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """The dimension worth one more question, and a pair that reads it.

    Degrades by disappearing. If nothing in the loved set isolates the axis
    that matters, try the next axis; if nothing isolates any of them, offer no
    refinement at all -- the result already shown is complete, which is the
    whole reason this stage sits after it.
    """
    order = sorted(sensitivity(est).items(), key=lambda kv: -kv[1])
    for dimension, moved in order:
        if moved == 0:
            break  # nothing below this reorders anything either
        pair = pair_for(est, dimension, used=used)
        if pair:
            return dimension, *pair
    return None


def apply_comparisons(
    est: "Estimate",
    comparisons: list[dict[str, str]],
    rows: list[dict[str, Any]],
) -> "Estimate":
    """Fold pairwise answers into the point, bounded in total.

    A comparison carries more information than a verdict, so each one pulls
    half the distance to the winner's level. The *cumulative* displacement is
    then capped at scoring.CLOSE -- a per-pair cap would not achieve this,
    since three permitted pulls can walk the point anywhere.

    The cap is a trade, not a parameter. Capping the best evidence in the
    pipeline below what it warrants is deliberate underweighting; it is right
    here only because the user is watching a result they have already been
    shown, and stability beats marginal accuracy while the list is visibly
    rearranging. If this stage ever runs *before* the result is shown, the cap
    comes off.
    """
    by_id = {r["game_id"]: r for r in rows}
    delta = {d: 0.0 for d in DIMENSIONS}
    for c in comparisons:
        winner, loser = by_id.get(c.get("winner")), by_id.get(c.get("loser"))
        if not winner or not loser:
            continue
        d = c.get("dimension") or contrastive(winner, loser)
        if d not in DIMENSIONS:
            continue
        delta[d] += COMPARISON_PULL * (winner[d] - est.dimensions[d].value)

    size = sum(v * v for v in delta.values()) ** 0.5
    if size > scoring.CLOSE:
        scale = scoring.CLOSE / size
        delta = {d: v * scale for d, v in delta.items()}

    dims = {
        d: DimensionEstimate(
            value=round(min(1.0, max(0.0, est.dimensions[d].value + delta[d])), 2),
            informative=est.dimensions[d].informative,
        )
        for d in DIMENSIONS
    }
    return Estimate(loved=est.loved, disliked=est.disliked,
                    unknown=est.unknown, dimensions=dims)
