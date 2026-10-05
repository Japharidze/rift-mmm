from r3m import blind


def _rows():
    lines = list(blind.kit_lines())
    # Twenty champions spread along the diagonal, one role each.
    return [{"champion_id": c, "name": c, "role": "top", "micro": i / 20, "meso": i / 20,
             "macro": i / 20} for i, c in enumerate(lines[:20])]


def test_every_champion_has_a_line_with_an_opener():
    for line in blind.kit_lines().values():
        assert line.startswith(("Up close: ", "From range: ", "Up close and from range: "))


def test_own_and_yoked_are_disjoint_and_three_each():
    rows = _rows()
    made = blind.cards((0.0, 0.0, 0.0), [(1, [0.1, 0.1, 0.1]), (2, [0.9, 0.9, 0.9])], rows, seed=7)
    assert made["yoked_session"] == 2           # the farthest
    assert made["yoke_min_met"]
    own = [c["champion_id"] for c in made["cards"] if c["source"] == "own"]
    yoked = [c["champion_id"] for c in made["cards"] if c["source"] == "yoked"]
    assert len(own) == len(yoked) == 3 and not set(own) & set(yoked)
    assert set(own) == {r["champion_id"] for r in rows[:3]}


def test_overlap_goes_to_the_next_ranked():
    rows = _rows()
    made = blind.cards((0.0, 0.0, 0.0), [(1, [0.0, 0.0, 0.0])], rows, seed=1)
    assert not made["yoke_min_met"]
    yoked = {c["champion_id"] for c in made["cards"] if c["source"] == "yoked"}
    assert yoked == {r["champion_id"] for r in rows[3:6]}


def test_order_is_seeded():
    rows = _rows()
    a = blind.cards((0.2, 0.2, 0.2), [(1, [0.9, 0.9, 0.9])], rows, seed=3)
    b = blind.cards((0.2, 0.2, 0.2), [(1, [0.9, 0.9, 0.9])], rows, seed=3)
    assert a["cards"] == b["cards"]


def test_nobody_to_yoke_to():
    assert blind.cards((0.5, 0.5, 0.5), [], _rows()) is None
