"""The card selector: value = P(recognised) x how much the answer would change.

docs/quiz-chain.md §4, "a card is a question". Synthetic rows only -- these
test the selection rules, not the labels.
"""

import math

import pytest

from r3m import quiz, selector


def game(gid, micro, meso, macro, *, reach=None, renown=None, tier="deck", parent=None):
    return {"game_id": gid, "name": gid, "micro": micro, "meso": meso, "macro": macro,
            "reach": reach, "renown": renown, "tier": tier, "parent_id": parent,
            "in_bank": True, "bias": None, "steam_appid": 1}


# A spread of games: a few famous, many obscure, one deep entry and one platform.
ROWS = [game(f"g{i}", (i * 37 % 100) / 100, (i * 53 % 100) / 100, (i * 71 % 100) / 100,
             reach=[20_000, 80_000, 300_000, 2_000_000, 9_000_000][i % 5]) for i in range(60)]
ROWS += [game("famous-a", 0.9, 0.8, 0.6, renown="universal"),
         game("famous-b", 0.1, 0.2, 0.9, renown="universal"),
         game("a-mode", 0.5, 0.5, 0.5, renown="universal", tier="deep", parent="famous-a"),
         game("a-platform", 0.5, 0.5, 0.5, renown="universal", tier="deep")]
CHAMPIONS = [{"champion_id": f"c{i}", "name": f"c{i}", "role": "mid",
              "micro": (i * 29 % 100) / 100, "meso": (i * 61 % 100) / 100, "macro": (i * 43 % 100) / 100}
             for i in range(40)]


def rnd(index, shown=(), played=(), loved=(), disliked=()):
    return selector.select_round(index, shown=list(shown), played=list(played), loved=list(loved),
                             disliked=list(disliked), reasons={}, rows=ROWS, champions=CHAMPIONS)


# -- priors ------------------------------------------------------------------

def test_renown_tiers_and_reach_share_one_scale():
    assert selector.recognition_prior({"renown": "universal"}) == 0.85
    assert selector.recognition_prior({"renown": "niche"}) == 0.25
    assert selector.recognition_prior({"reach": 20_000}) == pytest.approx(selector.PRIOR_LOW)
    assert selector.recognition_prior({"reach": 50_000_000}) == pytest.approx(selector.PRIOR_HIGH)
    assert selector.recognition_prior({"reach": 100_000}) < selector.recognition_prior({"reach": 1_000_000})
    assert selector.recognition_prior({}) == selector.PRIOR_LOW       # unknown: no invented fame


def test_a_player_who_recognises_more_than_expected_is_expected_to_know_more():
    by_id = {r["game_id"]: r for r in ROWS}
    shown = [f"g{i}" for i in range(10)]
    heavy, light = selector.breadth(shown, shown, by_id), selector.breadth(shown, [], by_id)
    assert heavy > 1 > light
    row = by_id["g2"]
    assert selector.recognition(row, heavy) > selector.recognition_prior(row) > selector.recognition(row, light)


# -- rounds ------------------------------------------------------------------------

def test_round_one_is_the_same_for_everyone_and_only_well_known():
    first = rnd(0)
    assert first == rnd(0)
    assert 0 < len(first) <= quiz.ROUND
    assert all(selector.recognition_prior(r) >= selector.ROUND_ONE_FLOOR for r in first)


def test_a_later_round_never_repeats_a_card_and_never_serves_deep_entries():
    first = [r["game_id"] for r in rnd(0)]
    second = rnd(1, shown=first, played=first[:3], loved=first[:2], disliked=first[2:3])
    ids = [r["game_id"] for r in second]
    assert len(ids) <= quiz.ROUND and len(set(ids)) == len(ids)
    assert not set(ids) & set(first)
    assert "a-mode" not in ids and "a-platform" not in ids


def test_with_equal_odds_and_nothing_left_to_read_a_card_that_moves_the_top_five_wins(monkeypatch):
    # Isolates the displacement term: answer odds held equal (far cards are
    # really less likely to be loved -- verdict_odds -- which is a separate
    # effect) and every dimension already read, so reading adds nothing.
    monkeypatch.setattr(selector, "verdict_odds", lambda row, point: (0.5, 0.5))
    loved = ["famous-a"]
    twin = game("twin", 0.9, 0.8, 0.6, renown="universal")
    far = game("far", 0.1, 0.1, 0.1, renown="universal")
    rows = ROWS + [twin, far]
    est = quiz.estimate(loved, [], rows=rows)
    read = quiz.Estimate(loved=est.loved, disliked=est.disliked, unknown=est.unknown, dimensions={
        d: quiz.DimensionEstimate(value=e.value, informative=5.0) for d, e in est.dimensions.items()})
    now = quiz._top(loved, [], {}, rows, CHAMPIONS)
    info = lambda r: selector.information(r, loved, [], {}, rows, CHAMPIONS, now, read)
    assert info(far) > info(twin)


def test_a_card_far_from_the_player_is_less_likely_to_be_loved():
    point = (0.9, 0.8, 0.6)
    near, far = game("n", 0.88, 0.8, 0.6), game("f", 0.1, 0.1, 0.1)
    assert selector.verdict_odds(near, point)[0] > 0.6 > selector.verdict_odds(far, point)[0]
    assert selector.verdict_odds(near, None) == (selector.P_LOVED, selector.P_DISLIKED)


def test_the_exploration_share_reaches_away_from_what_was_shown():
    # Show only one corner; the explored cards must land well away from it.
    corner = [r["game_id"] for r in ROWS if r["micro"] > 0.6 and r["meso"] > 0.6][:8]
    nxt = rnd(1, shown=corner, played=corner[:2], loved=corner[:2])
    by_id = {r["game_id"]: r for r in ROWS}
    dist = lambda r: min(math.dist((r["micro"], r["meso"], r["macro"]),
                                   (by_id[g]["micro"], by_id[g]["meso"], by_id[g]["macro"])) for g in corner)
    n_explore = round(quiz.ROUND * selector.EXPLORE_SHARE)
    explored = nxt[-n_explore:]
    assert min(dist(r) for r in explored) > 0.25


def test_the_sweep_stops_after_max_rounds():
    assert rnd(quiz.MAX_ROUNDS) is None
