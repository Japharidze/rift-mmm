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
#
# Retained for `suggest_for` and the retry hook, which pick games to *serve*.
# It is no longer how evidence is weighed: see `opportunity`.
INFORMATIVE = 0.25

# A game whose largest demand is below this presents no demand at all, and the
# absence is then the thing on offer. See `opportunity`.
LOW_CORNER = 0.35
# Opportunity a dimension must accumulate before it counts as read, in the
# units `opportunity` returns: one game presenting the dimension in full, or
# two presenting half of it each.
#
# Was a count of answers. A count cannot express the thing that broke: three
# games can be answered about and still offer nothing to answer *with*.
#
# Raised from 2 once the grid replaced the three-item opener. A 28-card grid
# hands over many more picks than a handful of single cards did, and at 2 a
# typical grid cleared every dimension outright -- which skipped the fill stage
# almost always, and called an axis read on two observations. Measured over
# random picks from the grid, the fill stage now runs for 84% of five-pick
# sessions and 32% of eight-pick ones, and someone who tapped twelve games has
# genuinely been read and skips it.
NEEDED = 1.0
# Dislike is real evidence, but noisier than delight.
DISLIKE_WEIGHT = 0.5

# What a player can say made a love stick (docs/quiz-chain.md §5). Only the
# first is about the game's demand; the rest are real reasons to love a game
# that no champion can deliver, so for matching they are noise.
LOVE_REASONS = ("gameplay", "people", "world", "nostalgia", "what_i_had")
# What put them off. The last two cancel the dislike: "never really played it"
# means it was never evidence, "not the gameplay" means it was about the art or
# the setting, which says nothing about the three dimensions.
DISLIKE_REASONS = ("gameplay", "never_played", "not_gameplay")
# Where a person reads them. One tap each, so short, and in the player's words.
REASON_LABELS = {
    "love": {
        "gameplay": "How it plays",
        "people": "The people I played with",
        "world": "The world or the story",
        "nostalgia": "Nostalgia",
        "what_i_had": "It was what I had",
    },
    "dislike": {
        "gameplay": "How it plays",
        "never_played": "I never really played it",
        "not_gameplay": "Something else - the look, the setting",
    },
}
WHY_QUESTION = {"love": "What made it stick?", "dislike": "What put you off?"}

# How much a love counts when nobody asked why, by how easily the game is loved
# for something other than its demand (bank/bias.yaml). Starting points, not
# fits: round 2 of the panel measures how often loves of each level turn out to
# be about the gameplay, and these follow that. Unrated games get no discount --
# no prior is better than an invented one.
UNCONFIRMED = {"low": 1.0, "medium": 0.75, "high": 0.4}


def love_weight(row: dict[str, Any], reason: str | None) -> float:
    if reason == "gameplay":
        return 1.0
    if reason in LOVE_REASONS:
        return 0.0
    return UNCONFIRMED.get(row.get("bias"), 1.0)


def dislike_weight(reason: str | None) -> float | None:
    """Multiplier on DISLIKE_WEIGHT; None removes the dislike altogether."""
    if reason == "never_played":
        return None
    if reason == "not_gameplay":
        return 0.0
    return 1.0


def opportunity(row: dict[str, Any], dimension: str) -> float:
    """How much chance this game gave the player to express a taste here.

    A game's coordinate on a dimension is how much *demand* it presents there
    (anchors/games.yaml, on converting Surnex's categories: his groupings are
    about proportion, this scale is about magnitude). Demand presented is
    therefore also opportunity offered -- Factorio has no opponent, so loving
    it expresses nothing about meso, not because low coordinates were decided
    to be weak evidence but because there was nothing there to love or reject.

    One clause, stated as a claim rather than bolted on: a game low on every
    dimension presents a different thing -- the absence of demand itself --
    and loving *that* is evidence for a low-demand taste. It is why Animal
    Crossing is informative about a relaxed player and Factorio is not
    informative about meso, though both score about 0.13 on it.
    """
    presence = max(row[d] for d in DIMENSIONS)
    if presence < LOW_CORNER:
        return 1.0 - presence
    return float(row[dimension])


def demand(row: dict[str, Any], dimension: str) -> float:
    """How much of this one dimension the game presents.

    Distinct from `opportunity`, and the difference is the low-corner clause.
    Loving Minecraft creative is real evidence -- for a low-demand taste
    across the board -- so its *opportunity* is high on every dimension. But
    it cannot settle meso specifically, because it contains none. Weighing
    evidence asks what a game can tell us; choosing what to serve asks what
    this dimension needs, and only the second wants the raw coordinate.
    """
    return float(row[dimension])


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
    reasons: dict[str, str] | None = None,
) -> Estimate:
    if rows is None:
        with db.connect() as conn:
            rows = db.game_points(conn)
    by_id = {r["game_id"]: r for r in rows}
    disliked = disliked or []
    reasons = reasons or {}

    liked_rows = [by_id[g] for g in loved if g in by_id]
    # "Never really played it" was never evidence, so it leaves the dislikes
    # entirely rather than staying at zero weight.
    disliked_rows = [by_id[g] for g in disliked
                     if g in by_id and dislike_weight(reasons.get(g)) is not None]
    unknown = [g for g in (*loved, *disliked) if g not in by_id]

    if not liked_rows:
        # Without something enjoyed there is no positive anchor, and an
        # estimate built only from reflections of dislikes would be a guess
        # wearing a number.
        raise ValueError("need at least one game you enjoyed")
    love_w = {r["game_id"]: love_weight(r, reasons.get(r["game_id"])) for r in liked_rows}
    if not any(love_w.values()):
        # Every love was for the people, the world or the memory. That is no
        # signal about how they play, and filling it with the midpoint is the
        # imputation CLAUDE.md forbids -- so it is the same error as no love.
        raise ValueError(
            "every game you loved, you loved for something other than how it plays "
            "-- pick one you loved for the gameplay itself"
        )

    dims = {}
    for d in DIMENSIONS:
        total = weight = 0.0
        for r in liked_rows:
            w = love_w[r["game_id"]] * opportunity(r, d)
            total += w * r[d]
            weight += w
        for r in disliked_rows:
            # A dislike rejects the demand that game presented and nothing
            # else: bouncing off osu! says you wanted less execution, and says
            # nothing about mind-games, because osu! never asked for any.
            #
            # The reflection is capped at the level presented. Plain 1 - x is
            # only a reflection when x is above the midpoint; below it, it
            # argues the player wanted *more* of a thing the game never
            # offered, so disliking osu! used to raise meso. Rejecting a demand
            # cannot be evidence for wanting more of it, so the target is at
            # most what was on offer.
            w = DISLIKE_WEIGHT * dislike_weight(reasons.get(r["game_id"])) * opportunity(r, d)
            total += w * min(1.0 - r[d], r[d])
            weight += w
        # Accumulated opportunity *is* how much was read, so it is the same
        # number that weighs the evidence. Nothing to keep in step.
        dims[d] = DimensionEstimate(
            value=round(total / weight, 2) if weight else 0.5,
            informative=round(weight, 2),
        )

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
    candidates = [r for r in servable(rows) if r["game_id"] not in exclude]
    # By demand, not by distance from the middle. A game far *below* the
    # midpoint is as far from it as one far above and presents none of the
    # dimension, so offering it to settle that dimension asks a question it
    # cannot answer.
    #
    # Filtered, not just sorted: returning fewer is better than padding the
    # list with games that cannot settle anything. A bank thin on a dimension
    # should say so by offering less, which is also the signal that the bank
    # needs that pole filled.
    useful = [r for r in candidates if demand(r, dimension) >= 0.5 + INFORMATIVE]
    return sorted(useful, key=lambda r: -demand(r, dimension))[:n]


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
    by_id = {r["game_id"]: r for r in servable(rows)}
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
    return max(candidates, key=lambda r: demand(r, target))


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
    pool = servable(rows)
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


def servable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Games that may appear as a card: the deck tier, in the bank.

    A deep entry (a mode or a platform game, bank/hand.yaml) is what a deck pick
    opens into and never a first-screen card -- with one exception: while its
    parent has no label, it stands in for the parent. Minecraft and Pokémon are
    labelled only through their deep entries (creative, VGC) until the new deck
    is labelled; excluding those would silently take Minecraft off the grid.
    The stand-in ends by itself the moment the parent has a label. Platforms
    (Roblox, Garry's Mod) have no parent and never stand in.
    """
    labelled = {r["game_id"] for r in rows}
    return [
        r for r in rows
        if r.get("in_bank", True) and (
            r.get("tier", "deck") == "deck"
            or (r.get("parent_id") and r["parent_id"] not in labelled)
        )
    ]


# Rounds of the recognition sweep (docs/quiz-chain.md §3). The same order for
# everyone for now: with ~47 labelled games, three rounds already show three
# quarters of the bank, so there is nothing to choose between. Rounds become
# per-player once the new deck is labelled.
# Fourteen, not twelve: the 42 labelled games people did tap in the panel fit
# three rounds exactly, so none is dropped for its position. Seven rows of two
# on a phone.
ROUND = 14
MAX_ROUNDS = 3
# Recognised games (loved, fine or disliked) after which, if every dimension is
# also read, another round costs more attention than it returns.
ENOUGH_RECOGNISED = 8
# Shown in panel round 1 (2026-09-26, 16 sessions, the whole 28-card grid) and
# tapped by nobody, loved or bounced. That is the only recognition evidence the
# project has for the segment, so these go to the back of the rounds instead of
# spending round 1 on cards people pass over. Spread alone put two of them in
# round 1. A proper recognition order (Steam reach, panel tap rates) comes with
# the labelled deck; this is the part the evidence already settles.
NEVER_TAPPED = frozenset({
    "animal-crossing", "cookie-clicker", "fall-guys", "marvel-rivals",
    "pokemon-vgc", "stardew-valley", "tetris-99",
})


def next_round(
    index: int,
    *,
    played: list[str],
    loved: list[str],
    disliked: list[str],
    reasons: dict[str, str],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Cards for round `index` (0-based), or None when the sweep should stop.

    The first round always runs. After it the sweep stops once enough games are
    recognised and every dimension is read -- so someone who has played a lot
    answers one round, someone who recognises little sees two or three.
    """
    # Dealt like a deck, not cut in order. The spread order runs from the
    # extremes to the middle, and the middle is where the mainstream lives
    # (grid's docstring): cut into consecutive rounds, CS2, League and Valorant
    # all fell past round 3 and were never shown. Dealt round-robin, every
    # round is a cross-section -- extremes and mainstream -- so round 1 alone is
    # a fair sample for a player who stops after it.
    spread = grid(rows, n=len(rows))
    main = [r for r in spread if r["game_id"] not in NEVER_TAPPED]
    last = [r for r in spread if r["game_id"] in NEVER_TAPPED]
    count = min(MAX_ROUNDS, max(1, -(-len(main) // ROUND)))
    rounds = [main[i::count] for i in range(count)]
    # Never-tapped cards only fill room left in the last round. The rest stay in
    # the bank for the fill stage, which serves them only when they would read
    # a dimension -- appended outright, they made round 3 twenty cards long.
    rounds[-1] = rounds[-1] + last[:max(0, ROUND - len(rounds[-1]))]
    rounds = [r for r in rounds if r]
    if index >= len(rounds):
        return None
    if index > 0 and len(played) >= ENOUGH_RECOGNISED and loved:
        try:
            est = estimate(loved, disliked, rows=rows, reasons=reasons)
        except ValueError:
            est = None
        if est is not None and not est.unread:
            return None
    return rounds[index]


# Follow-up questions in the whole quiz. Each costs a screen, so they go where
# the answer changes the result and nowhere else.
WHY_MAX = 3
# Top-five champions an answer must be able to displace to be worth asking.
WHY_IMPACT = 1


def _top(loved: list[str], disliked: list[str], reasons: dict[str, str],
         rows: list[dict[str, Any]], champions: list[dict[str, Any]]) -> set[str] | None:
    try:
        est = estimate(loved, disliked, rows=rows, reasons=reasons)
    except ValueError:
        return None
    return {m.champion_id for m in scoring.neighbourhood(est.point, n=5, rows=champions)}


def why_next(
    loved: list[str],
    disliked: list[str],
    reasons: dict[str, str],
    rows: list[dict[str, Any]],
    champions: list[dict[str, Any]],
    *,
    asked: int = 0,
) -> dict[str, Any] | None:
    """The one follow-up worth asking next, or None.

    Candidates: loves of bias-prone games (high, then medium) and dislikes,
    none already answered. Low-bias loves are never asked -- nobody loves osu!
    for its story. A candidate is worth a screen only if its two possible
    answers lead to different top-five champions: counting it in full against
    not at all for a love, keeping against removing for a dislike. Whichever
    moves the most is asked; ties go to high loves, then dislikes, then medium
    loves. An answer that could remove the last counting love moves everything,
    so it is always worth asking.
    """
    if asked >= WHY_MAX:
        return None
    by_id = {r["game_id"]: r for r in rows}
    candidates: list[tuple[int, int, str, str]] = []
    for g in loved:
        bias = by_id.get(g, {}).get("bias")
        if g in reasons or bias not in ("high", "medium"):
            continue
        yes = _top(loved, disliked, {**reasons, g: "gameplay"}, rows, champions)
        no = _top(loved, disliked, {**reasons, g: "people"}, rows, champions)
        impact = 5 if no is None else len(yes - no) if yes else 0
        candidates.append((impact, 0 if bias == "high" else 2, g, "love"))
    for g in disliked:
        if g in reasons or g not in by_id:
            continue
        keep = _top(loved, disliked, {**reasons, g: "gameplay"}, rows, champions)
        drop = _top(loved, disliked, {**reasons, g: "never_played"}, rows, champions)
        impact = len(keep - drop) if keep and drop else 0
        candidates.append((impact, 1, g, "dislike"))

    worth = [c for c in candidates if c[0] >= WHY_IMPACT]
    if not worth:
        return None
    _, _, game, kind = max(worth, key=lambda c: (c[0], -c[1]))
    options = LOVE_REASONS if kind == "love" else DISLIKE_REASONS
    return {"game_id": game, "kind": kind, "options": list(options)}


def fill_item(
    served: list[str],
    loved: list[str],
    disliked: list[str],
    rows: list[dict[str, Any]],
    asked: int = 0,
    reasons: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Stage 2: one more card, or None when there is nothing left to read.

    Unlike `next_item` there is no opener -- the grid was the opener -- and the
    budget counts only what this stage served, not the whole grid. Returns None
    the moment every dimension is read, so the common case is that this stage
    does not run at all.
    """
    if asked >= FILL_MAX or not loved:
        return None
    try:
        est = estimate(loved, disliked, rows=rows, reasons=reasons)
    except ValueError:
        return None  # no love counts: nothing to fill toward, the result says so
    if not est.unread:
        return None
    target = min(est.unread, key=lambda d: est.dimensions[d].informative)

    candidates = [r for r in servable(rows) if r["game_id"] not in served]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: demand(r, target))
    # A card that presents none of the open dimension is not worth a screen:
    # answering about it, either way, leaves the dimension exactly as unread.
    return best if demand(best, target) >= 0.5 + INFORMATIVE else None


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
