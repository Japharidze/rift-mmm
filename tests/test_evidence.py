"""Slice 1: stop counting the wrong things (docs/quiz-chain.md §3, §5).

Written before the code. Every rule here only removes or weakens evidence --
none adds a new direction -- which is what makes it safe to ship first:

- "fine" is recognition without taste: it never reaches the estimator.
- A love counts in full when it was the gameplay, and not at all when it was
  the people, the world, nostalgia or what was available.
- A love nobody asked about is discounted by how bias-prone the game is.
- A dislike that was "never really played" or "not about the gameplay" is
  removed.
- A "why" is asked only where its answer changes the top five champions.

Coordinates are hard-coded on purpose: these test the rules, not the labels.
"""

import pytest

from r3m import quiz

GAMES = [
    # id              micro meso  macro  bias      tier    parent
    ("cs2",            0.93, 0.72, 0.55, "medium", "deck", None),
    ("osu",            1.00, 0.07, 0.13, "low",    "deck", None),
    ("factorio",       0.17, 0.12, 0.92, "low",    "deck", None),
    ("stardew-valley", 0.12, 0.14, 0.77, "high",   "deck", None),
    ("among-us",       0.05, 0.90, 0.20, "high",   "deck", None),
    ("chess",          0.02, 0.53, 0.93, "medium", "deck", None),
    ("rps",            0.02, 0.91, 0.07, "high",   "deck", None),
    ("unrated",        0.60, 0.60, 0.60, None,     "deck", None),
    ("mc-creative",    0.13, 0.01, 0.23, "high",   "deep", "minecraft"),  # parent unlabelled
    ("chess-blitz",    0.70, 0.60, 0.70, "low",    "deep", "chess"),      # parent labelled
    ("roblox",         0.40, 0.40, 0.40, None,     "deep", None),         # platform
]
ROWS = [
    {"game_id": g, "micro": a, "meso": b, "macro": c, "bias": bias, "tier": tier,
     "parent_id": parent, "in_bank": True}
    for g, a, b, c, bias, tier, parent in GAMES
]
CHAMPIONS = [
    {"champion_id": f"c{i}", "name": f"c{i}", "role": "mid", "micro": a, "meso": b, "macro": c}
    for i, (a, b, c) in enumerate([
        (0.9, 0.7, 0.5), (0.85, 0.75, 0.6), (0.2, 0.2, 0.9), (0.1, 0.2, 0.8), (0.3, 0.9, 0.3),
        (0.2, 0.85, 0.2), (0.6, 0.6, 0.6), (0.5, 0.5, 0.5), (0.95, 0.1, 0.2), (0.4, 0.3, 0.9),
    ])
]


@pytest.fixture(autouse=True)
def whole_bank_serving(monkeypatch):
    # These fixtures are not panel games; most tests here exercise the bank
    # rules. The panel-round-1 mode has its own tests below.
    monkeypatch.setattr(quiz, "SERVING", "bank")


def point(loved, disliked=(), reasons=None):
    return quiz.estimate(list(loved), list(disliked), rows=ROWS, reasons=reasons).point


# -- loves --------------------------------------------------------------------

def test_a_love_for_the_gameplay_counts_in_full():
    # "In full" = exactly as if the game carried no bias rating at all.
    unrated = [{**r, "bias": None} for r in ROWS]
    assert point(["osu", "stardew-valley"], reasons={"stardew-valley": "gameplay"}) == \
        quiz.estimate(["osu", "stardew-valley"], [], rows=unrated).point


@pytest.mark.parametrize("reason", ["people", "world", "nostalgia", "what_i_had"])
def test_a_love_for_anything_else_counts_for_nothing(reason):
    assert point(["cs2", "stardew-valley"], reasons={"stardew-valley": reason}) == point(["cs2"])


def test_an_unasked_high_love_is_discounted_not_dropped():
    full = point(["cs2", "stardew-valley"], reasons={"stardew-valley": "gameplay"})
    unasked = point(["cs2", "stardew-valley"])
    alone = point(["cs2"])
    # Between counting it fully and not at all, on the macro axis it moves.
    assert alone[2] < unasked[2] < full[2]


def test_an_unasked_low_love_counts_in_full():
    assert point(["cs2", "osu"]) == point(["cs2", "osu"], reasons={"osu": "gameplay"})


def test_an_unrated_game_gets_no_prior_rather_than_an_invented_one():
    assert point(["cs2", "unrated"]) == point(["cs2", "unrated"], reasons={"unrated": "gameplay"})


def test_the_discount_also_lowers_how_much_is_read():
    full = quiz.estimate(["stardew-valley"], [], rows=ROWS, reasons={"stardew-valley": "gameplay"})
    unasked = quiz.estimate(["stardew-valley"], [], rows=ROWS)
    assert unasked.dimensions["macro"].informative < full.dimensions["macro"].informative


def test_loves_that_all_count_for_nothing_are_no_signal_not_the_midpoint():
    with pytest.raises(ValueError):
        quiz.estimate(["stardew-valley", "among-us"], [], rows=ROWS,
                      reasons={"stardew-valley": "nostalgia", "among-us": "people"})


# -- dislikes -----------------------------------------------------------------

@pytest.mark.parametrize("reason", ["never_played", "not_gameplay"])
def test_a_cancelled_dislike_is_removed(reason):
    assert point(["cs2"], ["osu"], reasons={"osu": reason}) == point(["cs2"])


def test_a_dislike_about_the_gameplay_still_counts():
    # CS2 loved, the 0.4/0.4/0.4 row disliked: CS2 already sits above it on
    # all three, so nothing the loves say explains the dislike and it moves
    # the point. (A dislike the loves explain moves nothing whatever the
    # reason, so it could not show the reason being honoured.)
    assert point(["cs2"], ["roblox"], reasons={"roblox": "gameplay"}) == point(["cs2"], ["roblox"])
    assert point(["cs2"], ["roblox"]) != point(["cs2"])


# -- which "why" to ask -----------------------------------------------------------

def why(loved, disliked=(), reasons=None, asked=0):
    return quiz.why_next(list(loved), list(disliked), reasons or {}, ROWS, CHAMPIONS, asked=asked)


def test_a_low_love_is_never_asked_about():
    q = why(["osu", "factorio"])
    assert q is None or q["game_id"] not in ("osu", "factorio")


def test_a_high_love_whose_answer_moves_the_top_five_is_asked():
    # osu is low-bias, so stardew is the only love that can be asked about
    q = why(["osu", "stardew-valley"])
    assert q == {"game_id": "stardew-valley", "kind": "love", "options": list(quiz.LOVE_REASONS)}


def test_nothing_is_asked_twice_and_the_cap_holds():
    assert why(["cs2", "stardew-valley"], reasons={"stardew-valley": "gameplay"}) is None or \
        why(["cs2", "stardew-valley"], reasons={"stardew-valley": "gameplay"})["game_id"] != "stardew-valley"
    assert why(["cs2", "stardew-valley"], asked=quiz.WHY_MAX) is None


def test_nothing_is_asked_when_no_answer_changes_the_top_five():
    # Keeping or removing this dislike leaves the same five champions: a
    # question here would cost a screen and change nothing.
    assert why(["factorio"], ["cs2"]) is None


def test_a_dislike_is_asked_with_its_own_options(monkeypatch):
    monkeypatch.setattr(quiz, "WHY_IMPACT", 0)  # isolate the options from the geometry
    q = why(["factorio"], ["cs2"])
    assert q == {"game_id": "cs2", "kind": "dislike", "options": list(quiz.DISLIKE_REASONS)}


# -- what may be served -------------------------------------------------------

def test_deep_entries_stand_in_only_while_their_parent_has_no_label():
    ids = {r["game_id"] for r in quiz.servable(ROWS)}
    assert "mc-creative" in ids          # Minecraft itself is not labelled yet
    assert "chess-blitz" not in ids      # chess is, so the variant waits for a deep dive
    assert "roblox" not in ids           # a platform is never a card


# -- rounds -------------------------------------------------------------------

def test_rounds_are_the_same_for_everyone_and_start_with_round_one():
    first = quiz.next_round(0, played=[], loved=[], disliked=[], reasons={}, rows=ROWS)
    assert first and first == quiz.next_round(0, played=[], loved=[], disliked=[], reasons={}, rows=ROWS)
    assert len(first) <= quiz.ROUND


def test_rounds_stop_early_once_enough_is_recognised_and_read(monkeypatch):
    monkeypatch.setattr(quiz, "ROUND", 3)
    monkeypatch.setattr(quiz, "ENOUGH_RECOGNISED", 3)
    # cs2 + osu read micro, chess + factorio read macro, together they read meso
    played = ["cs2", "osu", "chess", "factorio"]
    assert quiz.next_round(1, played=played, loved=played, disliked=[], reasons={}, rows=ROWS) is None
    # recognising little keeps the rounds coming
    assert quiz.next_round(1, played=["cs2"], loved=["cs2"], disliked=[], reasons={}, rows=ROWS)


def test_cards_nobody_tapped_in_the_panel_go_to_the_back(monkeypatch):
    monkeypatch.setattr(quiz, "ROUND", 3)
    monkeypatch.setattr(quiz, "MAX_ROUNDS", 5)
    rounds, i = [], 0
    while (cards := quiz.next_round(i, played=[], loved=[], disliked=[], reasons={}, rows=ROWS)):
        rounds.append([r["game_id"] for r in cards]); i += 1
    order = [g for r in rounds for g in r]
    assert "stardew-valley" in quiz.NEVER_TAPPED
    assert order[-1] == "stardew-valley"   # the only never-tapped game in these rows


def test_no_round_is_ever_larger_than_a_round():
    # A 300-game bank dealt into three uncapped rounds gave ~100 cards each.
    big = [{"game_id": f"g{i}", "micro": (i * 37 % 100) / 100, "meso": (i * 53 % 100) / 100,
            "macro": (i * 71 % 100) / 100, "bias": None, "tier": "deck", "parent_id": None,
            "in_bank": True} for i in range(300)]
    for i in range(quiz.MAX_ROUNDS):
        cards = quiz.next_round(i, played=[], loved=[], disliked=[], reasons={}, rows=big)
        assert cards is not None and len(cards) <= quiz.ROUND


# -- panel-round-1 serving ------------------------------------------------------

def _panel_rows():
    ids = sorted(quiz.PANEL_ROUND_1_BANK) + ["to-the-moon", "naruto-storm-4"]  # two new bank games
    return [{"game_id": g, "micro": (i * 37 % 100) / 100, "meso": (i * 53 % 100) / 100,
             "macro": (i * 71 % 100) / 100, "bias": None,
             "tier": "deep" if g in ("minecraft-creative", "pokemon-vgc", "tetris-99") else "deck",
             "parent_id": None, "in_bank": True} for i, g in enumerate(ids)]


def test_panel_rounds_are_exactly_round_ones_28_cards(monkeypatch):
    monkeypatch.setattr(quiz, "SERVING", "panel-round-1")
    rows = _panel_rows()
    shown = []
    for i in range(quiz.MAX_ROUNDS):
        cards = quiz.next_round(i, played=[], loved=[], disliked=[], reasons={}, rows=rows)
        if cards:
            assert len(cards) <= quiz.ROUND
            shown += [c["game_id"] for c in cards]
    assert set(shown) == quiz.PANEL_ROUND_1_CARDS and len(shown) == 28
    assert set(quiz.NEVER_TAPPED) <= set(shown)        # the dead cards are back, as in round 1


def test_panel_fill_draws_only_from_round_ones_bank(monkeypatch):
    monkeypatch.setattr(quiz, "SERVING", "panel-round-1")
    ids = {r["game_id"] for r in quiz.servable(_panel_rows())}
    assert ids == set(quiz.PANEL_ROUND_1_BANK)
    assert "to-the-moon" not in ids


def test_panel_serving_shows_every_player_all_of_round_ones_cards(monkeypatch):
    # A player who recognised plenty and is read on every dimension still gets
    # round 2: panel round 2 compares players on one fixed card set.
    monkeypatch.setattr(quiz, "SERVING", "panel-round-1")
    rows = [{"game_id": g, "name": g, "micro": (i * 37 % 100) / 100, "meso": (i * 53 % 100) / 100,
             "macro": (i * 71 % 100) / 100, "in_bank": True, "tier": "deck", "parent_id": None,
             "bias": None, "steam_appid": 1}
            for i, g in enumerate(quiz.PANEL_ROUND_1_CARDS)]
    first = quiz.next_round(0, played=[], loved=[], disliked=[], reasons={}, rows=rows)
    ids = [r["game_id"] for r in first]
    second = quiz.next_round(1, played=ids, loved=ids[:6], disliked=[], reasons={}, rows=rows)
    assert second, "stopped after round 1"
    assert len(first) + len(second) == len(quiz.PANEL_ROUND_1_CARDS)
