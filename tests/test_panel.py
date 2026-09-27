"""The comparison pass: parsing what testers typed, placing what they play, and
refusing to call a winner on too few players.

No network and no database: a fake Riot API and hand-built rows. Numbers are
chosen so each assertion can be checked by hand, not taken from real labels.
"""

import httpx

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
]


def _404() -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.invalid")
    return httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))


class FakeApi:
    def __init__(self, accounts: dict[tuple[str, str], str], games: list[tuple[str, str]]):
        self.accounts, self.games = accounts, games

    def account_by_riot_id(self, name: str, tag: str) -> dict:
        if (name, tag) not in self.accounts:
            raise _404()
        return {"puuid": self.accounts[(name, tag)]}

    def match_ids(self, puuid: str, *, count: int, queue: int) -> list[str]:
        # every game shows up under one queue only, as it would for real
        return [f"EUN1_{i}" for i in range(len(self.games))] if queue == 420 else []

    def match(self, match_id: str) -> dict:
        champion, position = self.games[int(match_id.split("_")[1])]
        return {"info": {"participants": [
            {"puuid": "someone-else", "championName": "Garen", "teamPosition": "TOP"},
            {"puuid": "p1", "championName": champion, "teamPosition": position},
        ]}}


def test_riot_id_spacing_around_the_hash_is_dropped():
    assert panel.riot_id_candidates("JohnRod #warud") == [("JohnRod", "warud", False)]


def test_a_missing_tag_is_guessed_from_the_region_defaults():
    assert panel.riot_id_candidates("basabee") == [("basabee", "EUNE", True), ("basabee", "EUW", True)]


def test_centroid_weights_by_games_and_falls_back_for_an_unlabelled_role():
    counts = {("Ahri", "mid"): 3, ("Karthus", "support"): 1, ("Mystery", "top"): 5}
    point, used = panel.centroid(counts, CHAMPIONS)
    # Karthus support has no row: the mean of his two rows (0.4, 0.8, 0.8).
    # Mystery has no label at all and is left out.
    assert used == 4
    assert [round(x, 3) for x in point] == [0.7, 0.65, 0.5]


def test_a_session_resolves_a_guessed_tag_and_reports_against_the_baseline():
    api = FakeApi({("basabee", "EUW"): "p1"}, [("Ahri", "MIDDLE")] * 12 + [("Karthus", "JUNGLE")] * 3)
    session = {"id": 7, "riot_id": "basabee", "point": [0.5, 0.5, 0.5],
               "loved": ["cs2"], "disliked": [], "comparisons": [], "champions": [{"name": "Ahri"}]}
    variant = panel.Variant("current", CHAMPIONS, GAMES)
    check = panel.check_session(api, session, [variant])

    assert check.resolved == "basabee#EUW" and check.tag_guessed
    assert check.labelled_games == 15 and not check.thin
    v = check.by_variant["current"]
    assert v.main_rank == 1  # loving cs2 lands nearest Ahri, which is what they play most
    assert v.d_quiz < v.d_baseline


def test_an_unknown_account_is_reported_not_raised():
    api = FakeApi({}, [])
    session = {"id": 8, "riot_id": "Nobody#EUNE", "point": [0.5, 0.5, 0.5],
               "loved": ["cs2"], "disliked": [], "comparisons": [], "champions": []}
    check = panel.check_session(api, session, [panel.Variant("current", CHAMPIONS, GAMES)])
    assert check.error and "Nobody#EUNE" in check.error


def test_below_the_floor_the_report_says_sanity_check_and_names_no_winner():
    api = FakeApi({("a", "EUNE"): "p1"}, [("Ahri", "MIDDLE")] * 12)
    session = {"id": 1, "riot_id": "a#EUNE", "point": [0.5, 0.5, 0.5],
               "loved": ["cs2"], "disliked": [], "comparisons": [], "champions": []}
    variants = [panel.Variant("current", CHAMPIONS, GAMES), panel.Variant("other", CHAMPIONS, GAMES)]
    text = panel.report([panel.check_session(api, session, variants)] * 3, roster_size=3)
    assert "SANITY CHECK ONLY (n=3" in text
    assert "minus" not in text and "mean d(quiz)" not in text
