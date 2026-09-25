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

import pytest

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
    e = est(["animal-crossing", "cookie-clicker", "candy-crush"])
    for d in ("micro", "meso", "macro"):
        assert e.dimensions[d].read, f"{d} unread for a player who told us plenty"
    assert e.dimensions["micro"].value < 0.35
    assert e.dimensions["meso"].value < 0.35


def test_dislike_only_rejects_the_demand_that_game_presented():
    """Bouncing off osu! rejects the demand osu! presented -- micro -- and
    nothing else. It has meso 0.06 and macro 0.10, so it offered no opportunity
    to form a view on either, and neither may move.
    """
    before = est(["cs2", "tekken"])
    after = est(["cs2", "tekken"], ["osu"])
    assert after.dimensions["micro"].value < before.dimensions["micro"].value - 0.02, \
        "disliking osu! should lower micro"
    for d in ("meso", "macro"):
        assert abs(after.dimensions[d].value - before.dimensions[d].value) <= 0.02, \
            f"{d} moved on a dislike of a game that presented no {d} demand"
