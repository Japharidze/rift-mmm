"""The reading (bank/reading.yaml, r3m.reading): only what was clearly read,
every sentence traceable to one rule, and the same answers the same words."""

import re

from r3m import panel, quiz, reading

GAMES = [
    # id                micro meso macro
    ("rocket-league",   0.92, 0.68, 0.42),
    ("cs2",             0.87, 0.85, 0.63),
    ("hades",           0.70, 0.24, 0.53),
    ("stardew-valley",  0.12, 0.14, 0.77),
    ("animal-crossing", 0.12, 0.14, 0.18),
    ("factorio",        0.11, 0.08, 0.88),
    ("chess",           0.08, 0.46, 0.93),
]
ROWS = [{"game_id": g, "name": g.replace("-", " ").title(), "micro": a, "meso": b, "macro": c,
         "bias": None, "in_bank": True} for g, a, b, c in GAMES]


def estimate(loved, disliked=()):
    trace = []
    est = quiz.estimate(list(loved), list(disliked), rows=ROWS, trace=trace)
    return est, trace


def read(point, est, trace, deep=()):
    return reading.read_player(point, est, trace, list(deep), ROWS)


# -- the fixture -------------------------------------------------------------------------

def test_the_bank_has_the_approved_twenty_five_sentences():
    b = reading.bank()
    assert sum(len(v) for v in b["dimensions"].values()) == 12
    assert sum(1 for s in b["splits"].values() for k in s if k in "+-") == 4
    assert len(b["unread"]) == 3
    assert sum(len(v) for v in b["champions"].values()) == 6


def test_no_sentence_names_a_fourth_concept():
    text = str(reading.bank()).lower()
    for word in ("tempo", "aggress", "risk", "difficult", "caution", "careful"):
        assert word not in text, word


# -- only what was clearly read ---------------------------------------------------------------

def test_a_middling_value_gets_no_sentence():
    est, trace = estimate(["rocket-league", "stardew-valley"])
    assert not [s for s in read((0.55, 0.45, 0.58), est, trace) if s["rule"]["kind"] == "dimension"]


def test_strong_replaces_moderate_never_both():
    est, trace = estimate(["rocket-league", "cs2", "hades"])
    ids = [s["id"] for s in read((0.75, 0.5, 0.5), est, trace)]
    assert "micro-high-strong" in ids and "micro-high-moderate" not in ids
    assert "micro-high-moderate" in [s["id"] for s in read((0.65, 0.5, 0.5), est, trace)]


def test_an_unread_dimension_gets_its_unread_line_and_never_a_claim():
    est, trace = estimate(["hades"])          # one love: some dimensions stay unread
    unread = [d for d in quiz.DIMENSIONS if not est.dimensions[d].read]
    assert unread
    out = read((0.9, 0.9, 0.9), est, trace)   # far from the middle everywhere
    for d in unread:
        assert f"{d}-unread" in [s["id"] for s in out]
        assert not any(s["rule"].get("dimension") == d and s["rule"]["kind"] == "dimension" for s in out)


def test_a_low_sentence_names_only_loves_that_sit_low():
    est, trace = estimate(["stardew-valley", "animal-crossing", "factorio", "rocket-league"])
    s = next(s for s in read((0.2, 0.5, 0.5), est, trace) if s["id"] == "micro-low-strong")
    assert "Rocket League" not in s["text"] and s["rule"]["games"]


def test_every_sentence_traces_to_exactly_one_rule_and_one_template():
    est, trace = estimate(["rocket-league", "cs2", "stardew-valley", "chess"])
    deep = [{"question": "cs2-gun", "option": "awp"}, {"question": "hades-weapon", "option": "ranged"}]
    out = read((0.8, 0.62, 0.3), est, trace, deep)
    assert len({s["id"] for s in out}) == len(out) and out
    b = reading.bank()
    every = ([t for v in b["dimensions"].values() for t in v.values()]
             + [s[k] for s in b["splits"].values() for k in "+-"] + list(b["unread"].values()))
    as_pattern = lambda t: "^" + ".+".join(re.escape(p) for p in re.split(r"\{[a-z]+\}", t)) + "$"
    for s in out:
        r = s["rule"]
        template = {"dimension": lambda: b["dimensions"][r.get("dimension", "")][r.get("level", "")],
                    "split": lambda: b["splits"][r.get("split", "")][r.get("direction", "")],
                    "unread": lambda: b["unread"][r.get("dimension", "")]}[r["kind"]]()
        assert re.match(as_pattern(template), s["text"]), s["id"]
        assert sum(bool(re.match(as_pattern(t), s["text"])) for t in every) == 1, s["id"]


def test_the_same_answers_give_the_same_reading():
    est, trace = estimate(["rocket-league", "cs2", "chess"])
    assert read((0.8, 0.6, 0.7), est, trace) == read((0.8, 0.6, 0.7), *estimate(["rocket-league", "cs2", "chess"]))


# -- splits: observations, strong only ---------------------------------------------------------

def test_a_split_needs_two_agreeing_answers_and_a_high_parent():
    est, trace = estimate(["rocket-league", "cs2", "hades"])
    one = [{"question": "cs2-gun", "option": "awp"}]
    two = one + [{"question": "hades-weapon", "option": "ranged"}]
    mixed = one + [{"question": "hades-weapon", "option": "melee"}]
    split_ids = lambda out: [s["id"] for s in out if s["rule"]["kind"] == "split"]
    assert split_ids(read((0.8, 0.5, 0.5), est, trace, one)) == []          # one answer read back is no reading
    assert split_ids(read((0.8, 0.5, 0.5), est, trace, two)) == ["micro_split+"]
    assert split_ids(read((0.8, 0.5, 0.5), est, trace, mixed)) == []        # contradicting answers
    assert split_ids(read((0.55, 0.5, 0.5), est, trace, two)) == []         # parent not clearly high


# -- champion reasons ------------------------------------------------------------------------------

def _reasons(point, shown):
    est, trace = estimate(["rocket-league", "cs2", "hades", "chess"])
    return [[s["id"] for s in r] for r in reading.champion_reasons(point, est, trace, shown, ROWS)]


def test_a_champion_reason_needs_the_champion_on_the_players_side():
    shown = [("Riven", (0.78, 0.5, 0.5)), ("Nasus", (0.30, 0.5, 0.5)), ("Garen", (0.40, 0.5, 0.5))]
    assert _reasons((0.8, 0.5, 0.5), shown) == [["champ-micro-high"], [], []]


def test_a_reason_every_champion_shares_is_no_reason():
    # All three sit equally close on micro: nobody stands out, so nobody gets it.
    shown = [("A", (0.78, 0.5, 0.5)), ("B", (0.78, 0.4, 0.5)), ("C", (0.78, 0.6, 0.5))]
    assert _reasons((0.8, 0.5, 0.5), shown) == [[], [], []]


def test_standing_out_needs_a_real_margin_not_a_noise_win():
    player = (0.8, 0.5, 0.75)
    inside_noise = [("A", (0.78, 0.5, 0.5)), ("B", (0.76, 0.5, 0.5))]    # 0.02 closer: noise
    clear = [("A", (0.78, 0.5, 0.5)), ("B", (0.70, 0.5, 0.5))]           # 0.08 closer: real
    assert _reasons(player, inside_noise) == [[], []]
    assert _reasons(player, clear)[0] == ["champ-micro-high"]


def test_each_champion_gets_at_most_one_reason_and_they_can_differ():
    player = (0.8, 0.5, 0.75)
    shown = [("Mechanics", (0.80, 0.5, 0.60)), ("Planner", (0.66, 0.5, 0.75))]
    assert _reasons(player, shown) == [["champ-micro-high"], ["champ-macro-high"]]


# -- the report ----------------------------------------------------------------------------------------

def test_a_sentence_nobody_rejects_is_flagged_suspect_not_a_success():
    lines = "\n".join(panel.reading_lines({"micro-high-moderate": {"shown": 20, "not_me": 0},
                                           "macro-low-strong": {"shown": 20, "not_me": 6}}))
    assert "micro-high-moderate" in lines and "SUSPECT" in lines.split("micro-high-moderate")[1].split("\n")[0]
    assert "SUSPECT" not in lines.split("macro-low-strong")[1].split("\n")[0]
    assert "by dimension: macro 6/20 (30%), micro 0/20 (0%)" in lines
