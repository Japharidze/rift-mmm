"""Deep dives and comparisons before the reveal (2026-09-30).

The fixture tests check the rules bank/deep_dives.yaml states for itself, so a
later edit that breaks one fails here rather than drifting players quietly.
"""

import pytest

from r3m import quiz, scoring

ALLOWED = set(quiz.DIMENSIONS) | set(quiz.SPLITS)


def questions():
    return [(family, q) for family, f in quiz.deep_dives().items() for q in f["questions"]]


# -- the fixture -------------------------------------------------------------------

@pytest.mark.parametrize("family,q", questions(), ids=lambda x: x if isinstance(x, str) else x["id"])
def test_every_question_is_one_axis_two_opposite_equal_pulls(family, q):
    assert q["axis"] in ALLOWED, f"{q['id']} moves {q['axis']}, not one of the three or the two splits"
    assert q["size"] in quiz.DEEP_DIVE_SIZE
    assert len(q["options"]) == 2
    # A coin-flip answerer ends where they started.
    assert sorted(o["sign"] for o in q["options"]) == [-1, 1]


def test_question_ids_are_unique_and_every_family_names_its_games():
    ids = [q["id"] for _, q in questions()]
    assert len(ids) == len(set(ids))
    for f in quiz.deep_dives().values():
        assert f["games"] and f["name"]


# -- who is asked what ------------------------------------------------------------------

def test_only_a_game_loved_for_the_gameplay_is_asked_about():
    assert quiz.deep_dive_next(["hades"], {"hades": "nostalgia"}, []) is None
    assert quiz.deep_dive_next(["hades"], {"hades": "gameplay"}, [])["family"] == "hades"
    # No reason given counts as gameplay, as it does in the estimate.
    assert quiz.deep_dive_next(["hades"], {}, [])["family"] == "hades"
    # Several reasons: asked whenever "how it plays" is among them.
    assert quiz.deep_dive_next(["hades"], {"hades": ["world", "gameplay"]}, [])["family"] == "hades"
    assert quiz.deep_dive_next(["hades"], {"hades": ["world", "people"]}, []) is None
    # A variant belongs to its family.
    assert quiz.deep_dive_next(["chess-blitz"], {}, [])["family"] == "chess"


def test_at_most_two_families_in_the_order_they_were_loved_and_never_a_question_twice():
    loved = ["cs2", "hades", "chess"]
    answered, families = [], []
    while (q := quiz.deep_dive_next(loved, {}, answered)) is not None:
        answered.append({"question": q["id"], "option": None})   # skipping still counts as asked
        families.append(q["family"])
    assert list(dict.fromkeys(families)) == ["cs2", "hades"]
    assert len(answered) == len({a["question"] for a in answered})


# -- how answers move the point -------------------------------------------------------------

def _est(point=(0.5, 0.5, 0.5)):
    return quiz.Estimate(dimensions={d: quiz.DimensionEstimate(value=v, informative=1.0)
                                     for d, v in zip(quiz.DIMENSIONS, point)})


def test_an_answer_moves_its_axis_by_its_size_and_nothing_else():
    after = quiz.apply_deep_dives(_est(), [{"question": "cs2-between", "option": "buy"}])
    assert after.point == (0.5, 0.5, 0.58)
    after = quiz.apply_deep_dives(_est(), [{"question": "minecraft-pvp", "option": "own"}])
    assert after.point == (0.5, 0.46, 0.5)


def test_split_answers_and_skips_are_logged_but_move_nothing():
    answered = [{"question": "cs2-gun", "option": "awp"}, {"question": "cs2-rounds", "option": "lurk"},
                {"question": "hades-boons", "option": None}]
    assert quiz.apply_deep_dives(_est(), answered).point == (0.5, 0.5, 0.5)


def test_opposite_answers_to_one_question_cancel():
    up = quiz.apply_deep_dives(_est(), [{"question": "chess-time", "option": "fast"}])
    down = quiz.apply_deep_dives(up, [{"question": "chess-time", "option": "slow"}])
    assert down.point == (0.5, 0.5, 0.5)


# -- comparisons, now before the reveal ---------------------------------------------------------

ROWS = [
    {"game_id": "hi", "micro": 1.0, "meso": 0.5, "macro": 0.5},
    {"game_id": "lo", "micro": 0.0, "meso": 0.5, "macro": 0.5},
    {"game_id": "hi2", "micro": 1.0, "meso": 0.4, "macro": 0.5},
    {"game_id": "lo2", "micro": 0.0, "meso": 0.4, "macro": 0.5},
    {"game_id": "hi3", "micro": 1.0, "meso": 0.6, "macro": 0.5},
    {"game_id": "lo3", "micro": 0.0, "meso": 0.6, "macro": 0.5},
]


def test_no_single_comparison_moves_the_point_more_than_close():
    est = _est((0.0, 0.5, 0.5))
    after = quiz.apply_comparisons(est, [{"winner": "hi", "loser": "lo", "dimension": "micro"}], ROWS)
    assert after.point[0] == pytest.approx(scoring.CLOSE)   # 0.15 x 1.0 would be 0.15; capped


def test_agreeing_comparisons_add_up_past_close_now_the_cumulative_cap_is_off():
    est = _est((0.0, 0.5, 0.5))
    comps = [{"winner": w, "loser": l, "dimension": "micro"}
             for w, l in (("hi", "lo"), ("hi2", "lo2"), ("hi3", "lo3"))]
    assert quiz.apply_comparisons(est, comps, ROWS).point[0] > scoring.CLOSE
