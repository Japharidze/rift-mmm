"""What a loved game is evidence *for*.

Written before the fix, and expected to fail against the plain weighted mean.

The principle, from anchors/games.yaml's own note on the conversion: a game's
coordinate on a dimension is how much *demand* it presents there. So it is
also how much opportunity the player had to express a taste about that
dimension. Weight each vote by that opportunity.

Loving Factorio expresses almost nothing about meso -- not because low
coordinates were decided to be weak, but because Factorio presented nothing
there to love or reject.

Coordinates below are a snapshot of games-v2, hard-coded on purpose: these test
the estimator, not the labels, and should not start failing because a future
game relabel moved a number.
"""

from r3m import quiz

GAMES = [
    # id                 micro  meso  macro
    ("valheim",           0.42, 0.25, 0.68),
    ("factorio",          0.17, 0.12, 0.92),
    ("hades",             0.72, 0.23, 0.55),
    ("animal-crossing",   0.12, 0.14, 0.18),
    ("stardew-valley",    0.12, 0.14, 0.77),
    ("cookie-clicker",    0.05, 0.10, 0.30),
    ("candy-crush",       0.07, 0.20, 0.52),
    ("cs2",               0.93, 0.72, 0.55),
    ("tekken",            0.88, 0.78, 0.30),
    ("osu",               0.98, 0.06, 0.10),
]
ROWS = [
    {"game_id": g, "name": g, "mode": None, "in_bank": True,
     "micro": mi, "meso": me, "macro": ma}
    for g, mi, me, ma in GAMES
]


def est(loved, disliked=None):
    return quiz.estimate(loved, disliked or [], rows=ROWS)


def test_loving_builders_leaves_meso_unread():
    """Sergi's actual session. Valheim, Factorio and Hades are single-player or
    co-op: none has a human opponent, so none presents meso demand. The quiz
    reported a confident 0.32 and matched him to low-meso champions while he
    mains Thresh, Bard and Zilean.

    Meso must come back unread. Macro, which all three genuinely demand, must
    be read and high.
    """
    e = est(["valheim", "factorio", "hades"])
    assert not e.dimensions["meso"].read, "meso was read from games that present none"
    assert e.dimensions["macro"].read
    assert e.dimensions["macro"].value > 0.6


def test_low_corner_is_read_not_unread():
    """The one place the principle needs its own clause, stated as a claim: a
    game low on every dimension presents a different thing -- the absence of
    demand itself -- and loving that is evidence for a low-demand taste. That
    is Animal Crossing's actual information content, and it must not be
    confused with having had no opportunity to answer.
    """
    # Six loves, not three: at NEEDED 1.0 (2026-09-30) three games are the thin
    # evidence that must not read every dimension -- for any player, relaxed
    # or not. Six low-demand loves do, and read low.
    extra = [{"game_id": g, "name": g, "mode": None, "in_bank": True, "micro": a, "meso": b, "macro": c}
             for g, a, b, c in (("solitaire", 0.04, 0.12, 0.18), ("tic-tac-toe", 0.0, 0.07, 0.15),
                                ("minesweeper", 0.30, 0.10, 0.25))]
    e = quiz.estimate(["animal-crossing", "cookie-clicker", "candy-crush",
                       "solitaire", "tic-tac-toe", "minesweeper"], [], rows=ROWS + extra)
    for d in ("micro", "meso", "macro"):
        assert e.dimensions[d].read, f"{d} unread for a player who told us plenty"
    assert e.dimensions["micro"].value < 0.35
    assert e.dimensions["meso"].value < 0.35


def test_dislike_only_rejects_the_demand_that_game_presented():
    """Bouncing off osu! rejects the demand osu! presented -- micro -- and
    nothing else. It has meso 0.06 and macro 0.10, so it offered no opportunity
    to form a view on either, and neither may move at all: a game speaks only
    where it presents demand, the same rule that keeps loving Factorio silent
    on meso.
    """
    before = est(["cs2", "tekken"])
    after = est(["cs2", "tekken"], ["osu"])
    for d in ("meso", "macro"):
        assert after.dimensions[d].value == before.dimensions[d].value, \
            f"{d} moved on a dislike of a game that presented no {d} demand"


def test_a_dislike_the_loves_already_explain_moves_nothing():
    """A dislike says *too much on at least one* presented dimension.

    Tekken presents micro 0.88 and meso 0.78. The osu!-and-CS2 player sits
    above it on micro but below it on meso, so the dislike is already explained
    -- it was the mind-games -- and nothing moves, micro least of all. Until
    2026-09-30 the rule read the OR as an AND and dragged micro down.
    """
    before = est(["osu", "cs2"])
    assert before.dimensions["micro"].value > 0.88 - quiz.DISLIKE_MARGIN
    assert before.dimensions["meso"].value < 0.78 - quiz.DISLIKE_MARGIN
    assert est(["osu", "cs2"], ["tekken"]).point == before.point

    below = est(["hades", "valheim"])
    assert est(["hades", "valheim"], ["tekken"]).point == below.point


def test_an_unexplained_dislike_corrects_only_the_cheapest_dimension():
    """Above the game on every dimension it presents, so the loves explain
    nothing: the dislike corrects the one dimension that needs the smallest
    move -- here meso, 0.20 away against micro's 0.36 -- and leaves the rest.
    Which dimension it really was is the why question's to name.
    """
    rows = ROWS + [{"game_id": "brawler", "name": "brawler", "mode": None, "in_bank": True,
                    "micro": 0.60, "meso": 0.60, "macro": 0.10}]
    before = quiz.estimate(["cs2", "tekken"], [], rows=rows)
    after = quiz.estimate(["cs2", "tekken"], ["brawler"], rows=rows)
    assert after.dimensions["meso"].value < before.dimensions["meso"].value
    assert after.dimensions["micro"].value == before.dimensions["micro"].value
    assert after.dimensions["macro"].value == before.dimensions["macro"].value


def test_a_dimension_is_settled_by_games_that_present_it():
    """The retry hook and the fill stage pick what to *serve*. Ranking by
    distance from the midpoint treats a game far below it as just as useful as
    one far above, and the one below presents none of the dimension -- so the
    question it asks cannot settle anything.
    """
    for d in ("micro", "meso", "macro"):
        offered = quiz.suggest_for(d, exclude=[], rows=ROWS, n=3)
        for g in offered:
            assert g[d] >= 0.5, (
                f"offered {g['game_id']} ({d}={g[d]}) to settle {d}; it presents none"
            )


def test_an_unread_dimension_never_explains_a_match():
    """What was not read is said, not filled (CLAUDE.md). A player read only on
    macro must not be told they lean away from execution."""
    from r3m import scoring
    e = est(["factorio"])
    assert not e.dimensions["micro"].read and e.dimensions["micro"].value < 0.5 - quiz.INFORMATIVE
    match = scoring.Match(champion_id="x", name="X", role="mid", point=(0.1, 0.1, 0.1), distance=0.0)
    why = quiz.explain(e, match)
    assert why is None or "execution" not in why.lower()
