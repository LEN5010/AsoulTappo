"""The park link game's board rules (app/link.py) and the fixture the client is checked against."""
import json
import random
import time

import pytest

import gen_link_fixture
from app import link

E = link.EMPTY
# The example levels of server/economy.example.json (park.link.levels).
LEVELS = [(4, 6, 6, "none"), (6, 8, 12, "down"), (6, 10, 15, "center")]


def deck(kinds):
    return sorted(k for k in range(kinds) for _ in range(4))


def valid_line(board, rows, cols, p, a, b):
    """Whether corner list p is a line of at most three segments from cell a to cell b over empty cells."""
    if p[0] != divmod(a, cols) or p[-1] != divmod(b, cols) or not 2 <= len(p) <= 4:
        return False

    def free(r, c):
        return not (0 <= r < rows and 0 <= c < cols) or board[r * cols + c] == E

    for r, c in p:
        if not (-1 <= r <= rows and -1 <= c <= cols):
            return False
    for (r1, c1), (r2, c2) in zip(p, p[1:]):
        if (r1 == r2) == (c1 == c2):
            return False
        cells = ([(r1, c) for c in range(min(c1, c2) + 1, max(c1, c2))] if r1 == r2
                 else [(r, c1) for r in range(min(r1, r2) + 1, max(r1, r2))])
        if not all(free(r, c) for r, c in cells):
            return False
    return all(free(r, c) for r, c in p[1:-1])


def best_cost(board, rows, cols, a, b):
    """(turns, length) of the best line by trying every corner sequence on the board and its ring."""
    pts = [(r, c) for r in range(-1, rows + 1) for c in range(-1, cols + 1)]
    ends = divmod(a, cols), divmod(b, cols)
    found = None
    for mids in [()] + [(p,) for p in pts] + [(p, q) for p in pts for q in pts]:
        p = [ends[0], *mids, ends[1]]
        if valid_line(board, rows, cols, p, a, b):
            cost = (len(p) - 2, sum(abs(x[0] - y[0]) + abs(x[1] - y[1]) for x, y in zip(p, p[1:])))
            found = cost if found is None or cost < found else found
    return found


def test_the_client_fixture_is_what_the_rules_give():
    assert json.loads(gen_link_fixture.FIXTURE.read_text(encoding="utf-8")) == gen_link_fixture.build()


def test_fixture_covers_the_contract_cases():
    data = gen_link_fixture.build()
    turns = {len(c["path"]) - 2 for c in data["connect"] if c["path"]}
    assert turns == {0, 1, 2}
    assert any(c["path"] and any(r in (-1, c["rows"]) or k in (-1, c["cols"]) for r, k in c["path"])
               for c in data["connect"])
    assert {c["name"] for c in data["connect"] if c["path"] is None} >= {
        "blocked in a row", "three turns needed", "different kinds", "the same cell", "an empty cell"}
    assert {s["shift"] for s in data["shift"]} == set(link.SHIFTS)
    assert {s["shift"] for s in data["sequences"]} == set(link.SHIFTS)
    assert any(f["pair"] is None for f in data["find"]) and any(f["pair"] for f in data["find"])


def test_connect_paths_in_the_fixture_are_valid_lines():
    data = gen_link_fixture.build()
    cases = data["connect"] + [{**p, "name": "random", "rows": d["rows"], "cols": d["cols"], "board": d["board"]}
                               for d in data["boards"] for p in d["pairs"]]
    for c in cases:
        if c["path"]:
            path = [tuple(x) for x in c["path"]]
            assert valid_line(c["board"], c["rows"], c["cols"], path, c["a"], c["b"]), c["name"]


def test_connect_finds_the_fewest_turns_then_the_shortest_line():
    rng = random.Random(7)
    for _ in range(120):
        rows, cols = rng.randint(1, 4), rng.randint(1, 5)
        board = [rng.choice([E, 0, 1]) for _ in range(rows * cols)]
        for a in range(rows * cols):
            for b in range(rows * cols):
                if a == b or board[a] == E or board[a] != board[b]:
                    continue
                p = link.connect(board, rows, cols, a, b)
                want = best_cost(board, rows, cols, a, b)
                assert link.linked(board, rows, cols, a, b) == (want is not None)
                if want is None:
                    assert p is None
                else:
                    assert valid_line(board, rows, cols, p, a, b)
                    assert (len(p) - 2, sum(abs(x[0] - y[0]) + abs(x[1] - y[1]) for x, y in zip(p, p[1:]))) == want


def test_connect_refuses_bad_pairs():
    board = [0, 0, E, 1]
    assert link.connect(board, 1, 4, 0, 0) is None
    assert link.connect(board, 1, 4, 0, 2) is None
    assert link.connect(board, 1, 4, 0, 3) is None
    assert link.connect(board, 1, 4, 0, 9) is None
    assert link.connect([0, 0, 0, 0], 1, 4, 0.25, 0.75) is None
    assert link.connect([0, 0, 0, 0], 1, 4, True, 0) is None
    assert link.connect(board, 1, 4, 0, 1) == [(0, 0), (0, 1)]


def test_shift_and_remove_leave_the_input_alone():
    board = [0, E, 1, 1, E, 0, 2, 2]
    copy = list(board)
    for s in link.SHIFTS:
        link.apply_shift(board, 2, 4, s)
        link.remove_pair(board, 2, 4, s, 0, 5)
    assert board == copy
    assert link.remove_pair(board, 2, 4, "left", 0, 5) == [1, 1, E, E, 2, 2, E, E]
    assert link.remove_pair(board, 2, 4, "down", 2, 3) == [E, E, E, E, 0, 0, 2, 2]
    assert link.remove_pair(board, 2, 4, "center", 6, 7) == [E, 0, 1, 1, E, 0, E, E]


def test_center_needs_even_columns():
    with pytest.raises(ValueError):
        link.apply_shift([0, 0, E], 1, 3, "center")
    with pytest.raises(ValueError):
        link.apply_shift([0, 0], 1, 2, "up")


def test_find_pair_scans_in_index_order():
    # Both (0, 3) and (1, 2) link; a = 0 comes first. Then the 2x2 cross has none.
    assert link.find_pair([0, 1, 1, 0], 1, 4) == (0, 3)
    assert link.find_pair([0, 1, 1, 0], 2, 2) is None


def test_solvable_is_greedy_with_the_shift():
    assert link.solvable([0, 0, 1, 1], 1, 4, "none")
    assert not link.solvable([0, 1, 1, 0], 2, 2, "none")
    # Greedy play on this board gets stuck unless the tiles fall after each pair.
    board = [2, 0, 1, 0,
             1, 2, 0, 1,
             2, 2, 1, 0]
    assert {s: link.solvable(board, 3, 4, s) for s in link.SHIFTS} == {
        "none": False, "down": True, "left": False, "center": False}


@pytest.mark.parametrize("rows,cols,kinds", [(4, 6, 6), (6, 8, 12), (6, 10, 15)])
def test_reverse_placement_clears_in_reverse_order(rows, cols, kinds):
    for seed in range(15):
        board, pairs = link._reverse(rows, cols, kinds, random.Random(seed))
        assert link.generate(rows, cols, kinds, "none", random.Random(seed)) == board
        assert sorted(board) == deck(kinds)
        assert len(pairs) == kinds * 2
        for a, b in reversed(pairs):
            assert link.connect(board, rows, cols, a, b) is not None
            board = link.remove_pair(board, rows, cols, "none", a, b)
        assert all(t == E for t in board)


@pytest.mark.parametrize("rows,cols,kinds,shift", [(6, 8, 12, "down"), (6, 8, 12, "left"), (6, 10, 15, "center")])
def test_shifted_boards_are_solvable_or_hold_a_pair(rows, cols, kinds, shift):
    solved = 0
    for seed in range(30):
        board = link.generate(rows, cols, kinds, shift, random.Random(seed))
        assert sorted(board) == deck(kinds)
        assert link.find_pair(board, rows, cols) is not None
        solved += link.solvable(board, rows, cols, shift)
    # The attempt cap rarely runs out at these sizes; the time budget may on a loaded machine.
    assert solved >= 27


def test_shifted_fallback_still_holds_a_pair(monkeypatch):
    monkeypatch.setattr(link, "SOLVE_TRIES", 0)
    for seed in range(20):
        board = link.generate(6, 8, 12, "left", random.Random(seed))
        assert sorted(board) == deck(12)
        assert link.find_pair(board, 6, 8) is not None


def test_generate_checks_its_arguments():
    with pytest.raises(ValueError):
        link.generate(4, 6, 5, "none", random.Random(0))
    with pytest.raises(ValueError):
        link.generate(4, 6, 6, "up", random.Random(0))


def test_shuffle_keeps_the_tiles_and_leaves_a_pair():
    rng = random.Random(3)
    for seed in range(20):
        board = gen_link_fixture.random_board(6, 8, 12, 9, seed)
        out = link.shuffle(board, 6, 8, rng)
        assert sorted(out) == sorted(board)
        assert [t == E for t in out] == [t == E for t in board]
        assert link.find_pair(out, 6, 8) is not None


@pytest.mark.parametrize("board,rows,cols", [
    # No two tiles side by side: rows and columns hold one tile each, or two apart.
    ([0, E, E, E,
      E, E, 1, E,
      E, 1, E, E,
      E, E, E, 0], 4, 4),
    ([E, E, E,
      0, E, 1,
      E, E, E,
      1, E, 0], 4, 3),
    ([0, 1, 1, 0], 2, 2),
])
def test_shuffle_makes_a_pair_when_tries_run_out(monkeypatch, board, rows, cols):
    monkeypatch.setattr(link, "SHUFFLE_TRIES", 0)
    out = link.shuffle(board, rows, cols, random.Random(0))
    assert sorted(out) == sorted(board)
    assert [t == E for t in out] == [t == E for t in board]
    assert link.find_pair(out, rows, cols) is not None


@pytest.mark.parametrize("rows,cols,kinds,shift", LEVELS)
def test_generation_time_per_level(rows, cols, kinds, shift):
    # The server budget is about 50 ms a game on one core; the mean here is a loose check, not a benchmark.
    n = 20
    start = time.perf_counter()
    for seed in range(n):
        link.generate(rows, cols, kinds, shift, random.Random(seed))
    assert (time.perf_counter() - start) / n < 0.05


class Constant:
    """A generator stuck on one value: every restart of reverse placement repeats the last one."""

    def random(self):
        return 0.5


@pytest.mark.parametrize("rows,cols,kinds,shift", [(2, 4, 2, "none"), (4, 6, 6, "none"), (2, 4, 2, "left")])
def test_a_stuck_generator_still_ends(rows, cols, kinds, shift):
    board = link.generate(rows, cols, kinds, shift, Constant())
    assert sorted(board) == deck(kinds)
    assert link.find_pair(board, rows, cols) is not None


@pytest.mark.parametrize("rows,cols,kinds,shift", LEVELS + [(6, 8, 12, "left")])
def test_an_overrun_budget_still_deals_a_full_board_with_a_pair(monkeypatch, rows, cols, kinds, shift):
    monkeypatch.setattr(link, "BUDGET_S", 0)
    for seed in range(5):
        board = link.generate(rows, cols, kinds, shift, random.Random(seed))
        assert sorted(board) == deck(kinds)
        assert link.find_pair(board, rows, cols) is not None


@pytest.mark.parametrize("rows,cols,kinds,shift", [(12, 16, 48, "none"), (2, 840, 420, "center")])
def test_large_boards_keep_to_the_budget(rows, cols, kinds, shift):
    start = time.perf_counter()
    board = link.generate(rows, cols, kinds, shift, random.Random(1))
    # BUDGET_S plus the last pair check; loose so a busy machine does not fail it.
    assert time.perf_counter() - start < 0.5
    assert sorted(board) == deck(kinds)
    assert link.find_pair(board, rows, cols) is not None
