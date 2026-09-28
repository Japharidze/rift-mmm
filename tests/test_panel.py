"""The comparison pass: parsing what testers typed, placing what they play,
measuring against each main rather than their average, and refusing to call a
winner on too few players.

No network and no database: a fake Riot API and hand-built rows. Numbers are
chosen so each assertion can be checked by hand, not taken from real labels.
"""

import math

import httpx
import pytest

from r3m import panel

CHAMPIONS = [
    {"champion_id": "Ahri", "name": "Ahri", "role": "mid", "micro": 0.8, "meso": 0.6, "macro": 0.4},
    {"champion_id": "Karthus", "name": "Karthus", "role": "jungle", "micro": 0.4, "meso": 0.8, "macro": 0.9},
    {"champion_id": "Karthus", "name": "Karthus", "role": "mid", "micro": 0.4, "meso": 0.8, "macro": 0.7},
    {"champion_id": "Garen", "name": "Garen", "role": "top", "micro": 0.2, "meso": 0.2, "macro": 0.3},
]
GAMES = [
    {"game_id": "cs2", "micro": 0.9, "meso": 0.8, "macro": 0.6, "in_bank": True},
    {"game_id": "chess", "micro": 0.1, "meso": 0.6, "macro": 0.9, "in_bank": True},
    {"game_id": "cookie-clicker", "micro": 0.05, "meso": 0.1, "macro": 0.3, "in_bank": True},
]
CURRENT = [panel.Variant("current", CHAMPIONS, GAMES)]


def _404() -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.invalid")
    return httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))


class FakeApi:
    def __init__(self, accounts: dict[tuple[str, str], str], games: list[tuple[str, str]]):
        self.accounts, self.games, self.calls = accounts, games, 0

    def account_by_riot_id(self, name: str, tag: str) -> dict:
        self.calls += 1
        if (name, tag) not in self.accounts:
            raise _404()
        return {"puuid": self.accounts[(name, tag)]}

    def match_ids(self, puuid: str, *, count: int, queue: int) -> list[str]:
        self.calls += 1
        # every game shows up under one queue only, as it would for real
        return [f"EUN1_{i}" for i in range(len(self.games))] if queue == 420 else []

    def match(self, match_id: str) -> dict:
        self.calls += 1
        champion, position = self.games[int(match_id.split("_")[1])]
        return {"info": {"participants": [
            {"puuid": "someone-else", "championName": "Garen", "teamPosition": "TOP"},
            {"puuid": "p1", "championName": champion, "teamPosition": position},
        ]}}


class NoApi:
    """Any call is a failure: cached and stored mains must not touch Riot."""
    def __getattr__(self, name):
        raise AssertionError(f"Riot API called: {name}")


def _session(sid: int, riot_id: str, loved: list[str], mains=None) -> dict:
    return {"id": sid, "riot_id": riot_id, "point": [0.5, 0.5, 0.5], "loved": loved,
            "disliked": [], "comparisons": [], "champions": [{"name": "Ahri"}],
            "actual_mains": mains}


def test_riot_id_spacing_around_the_hash_is_dropped():
    assert panel.riot_id_candidates("JohnRod #warud") == [("JohnRod", "warud", False)]


def test_a_missing_tag_is_guessed_from_the_region_defaults():
    assert panel.riot_id_candidates("basabee") == [("basabee", "EUNE", True), ("basabee", "EUW", True)]


def test_an_unlabelled_role_falls_back_and_an_unlabelled_champion_is_left_out():
    placed = panel.MainPoints(CHAMPIONS).placed(
        [("Ahri", "mid", 3), ("Karthus", "support", 1), ("Mystery", "top", 5)])
    # Karthus support has no row: the mean of his two rows. Mystery: no label.
    assert [(c, g) for c, _, g in placed] == [("Ahri", 3), ("Karthus", 1)]
    assert placed[1][1] == pytest.approx((0.4, 0.8, 0.8))


def test_distance_is_to_each_main_not_to_their_average():
    # Two opposite mains, equally played. Their centroid is (0.5, 0.4, 0.35):
    # a point there would score ~0 against the centroid, yet it is far from
    # both champions actually played -- the flaw the first version had.
    placed = panel.MainPoints(CHAMPIONS).placed([("Ahri", "mid", 1), ("Garen", "top", 1)])
    middle = (0.5, 0.4, 0.35)
    expected = (math.dist(middle, (0.8, 0.6, 0.4)) + math.dist(middle, (0.2, 0.2, 0.3))) / 2
    assert panel.mean_distance(middle, placed) == pytest.approx(expected)
    assert panel.mean_distance(middle, placed) > 0.3


def test_a_main_at_the_quiz_point_ranks_first():
    placed = panel.MainPoints(CHAMPIONS).placed([("Ahri", "mid", 2)])
    assert panel.mean_rank((0.8, 0.6, 0.4), placed, CHAMPIONS) == 0.0


def test_a_fetch_resolves_a_guessed_tag_and_fills_the_cache():
    api = FakeApi({("basabee", "EUW"): "p1"}, [("Ahri", "MIDDLE")] * 12 + [("Karthus", "JUNGLE")] * 3)
    cache: dict = {}
    check = panel.check_session(api, _session(7, "basabee", ["cs2"]), CURRENT, cache=cache)

    assert check.resolved == "basabee#EUW" and check.tag_guessed and check.source == "fetched"
    assert check.mains[0] == ("Ahri", "mid", 12) and check.placed_games == 15
    assert cache["7"]["resolved"] == "basabee#EUW"
    v = check.by_variant["current"]
    assert v.rank is not None and v.dist is not None and v.dist_ref is not None


def test_cached_and_stored_mains_make_no_riot_calls():
    cache = {"7": {"riot_id": "basabee", "resolved": "basabee#EUW", "tag_guessed": True,
                   "mains": [["Ahri", "mid", 12]]}}
    from_cache = panel.check_session(NoApi(), _session(7, "basabee", ["cs2"]), CURRENT, cache=cache)
    assert from_cache.source == "cache" and from_cache.placed_games == 12

    stored = _session(9, "x#EUNE", ["cs2"], mains=[{"champion_id": "Garen", "role": "top", "games": 4}])
    from_db = panel.check_session(NoApi(), stored, CURRENT)
    assert from_db.source == "stored" and from_db.mains == [("Garen", "top", 4)]


def test_personal_fit_ranks_own_quiz_point_against_other_players():
    # Loving cs2 lands near Ahri; loving cookie clicker lands near Garen.
    ahri = _session(1, "a#EUNE", ["cs2"], mains=[{"champion_id": "Ahri", "role": "mid", "games": 10}])
    garen = _session(2, "g#EUNE", ["cookie-clicker"], mains=[{"champion_id": "Garen", "role": "top", "games": 10}])
    checks = [panel.check_session(NoApi(), s, CURRENT) for s in (ahri, garen)]
    assert panel.personal_fit(checks, "current") == {1: (1, 2), 2: (1, 2)}


def test_an_unknown_account_is_reported_not_raised():
    check = panel.check_session(FakeApi({}, []), _session(8, "Nobody#EUNE", ["cs2"]), CURRENT)
    assert check.error and "Nobody#EUNE" in check.error


def test_below_the_floor_the_report_says_sanity_check_and_gives_no_average():
    s = _session(1, "a#EUNE", ["cs2"], mains=[{"champion_id": "Ahri", "role": "mid", "games": 12}])
    variants = CURRENT + [panel.Variant("other", CHAMPIONS, GAMES)]
    checks = [panel.check_session(NoApi(), {**s, "id": i}, variants) for i in range(3)]
    text = panel.report(checks)
    assert "SANITY CHECK ONLY (n=3" in text
    assert "closest for" not in text and "minus" not in text
