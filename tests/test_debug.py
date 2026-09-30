"""The ?debug=1 view must describe the result that was actually computed."""

import pytest

from r3m import quiz

GAMES = [
    {"game_id": "cs2", "name": "CS2", "micro": 0.93, "meso": 0.72, "macro": 0.55, "bias": "medium"},
    {"game_id": "hades", "name": "Hades", "micro": 0.72, "meso": 0.23, "macro": 0.55, "bias": "medium"},
    {"game_id": "wow", "name": "WoW", "micro": 0.45, "meso": 0.40, "macro": 0.70, "bias": "high"},
    {"game_id": "tekken", "name": "Tekken", "micro": 0.88, "meso": 0.78, "macro": 0.30, "bias": None},
    {"game_id": "among-us", "name": "Among Us", "micro": 0.05, "meso": 0.90, "macro": 0.20, "bias": "high"},
]
CHAMPIONS = [{"champion_id": f"c{i}", "name": f"C{i}", "role": "mid",
              "micro": (i * 29 % 100) / 100, "meso": (i * 61 % 100) / 100, "macro": (i * 43 % 100) / 100}
             for i in range(30)]


def view(**kw):
    args = dict(loved=["cs2", "hades", "wow"], disliked=["tekken", "among-us"],
                reasons={"wow": ["world", "gameplay"]},
                deep=[{"question": "cs2-between", "option": "buy"}, {"question": "cs2-gun", "option": "awp"}],
                comparisons=[], rows=GAMES, champions=CHAMPIONS)
    args.update(kw)
    return quiz.debug_view(**args)


def test_the_final_point_is_the_point_matching_uses():
    d = view()
    est = quiz.estimate(["cs2", "hades", "wow"], ["tekken", "among-us"], rows=GAMES,
                        reasons={"wow": ["world", "gameplay"]})
    settled = quiz.settle(est, [{"question": "cs2-between", "option": "buy"},
                                {"question": "cs2-gun", "option": "awp"}], [], GAMES)
    assert d["points"]["final"] == list(settled.point)
    assert d["points"]["verdicts"] == list(est.point)


def test_each_dimensions_shares_add_up_to_the_whole():
    d = view()
    for dim in quiz.DIMENSIONS:
        shares = [g["dims"][dim]["share"] for g in d["evidence"] if dim in g["dims"]]
        assert sum(shares) == pytest.approx(1.0, abs=0.01)


def test_it_shows_what_counted_what_was_explained_and_what_was_only_logged():
    d = view()
    by = {g["game"]: g for g in d["evidence"]}
    assert by["wow"]["reason"] == ["world", "gameplay"] and by["wow"]["love_weight"] == 1.0
    assert by["hades"]["love_weight"] == quiz.UNCONFIRMED["medium"]
    assert any(g["explained"] for g in d["evidence"] if g["kind"] == "dislike")
    dives = {q["axis"]: q for q in d["deep_dives"]}
    assert dives["macro"]["move"] == 0.08 and dives["micro_split"]["logged_only"]
    assert len(d["champions"]) == 10
