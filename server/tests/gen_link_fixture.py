"""Writes client/src/panel/park/link.fixture.json, the link game cases both app/link.py and client/src/panel/park/link.ts
are checked against (tests/test_link.py, link.test.ts). Run from server/: PYTHONPATH=. .venv/bin/python
tests/gen_link_fixture.py. The output depends only on app/link.py and the fixed seeds here."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from app import link

FIXTURE = Path(__file__).resolve().parents[2] / "client/src/panel/park/link.fixture.json"
E = link.EMPTY


def parse(art: str) -> tuple[list[int], int, int]:
    """A board drawn as lines of cells: '.' is empty, a letter is a kind (A is 0)."""
    lines = [ln.strip() for ln in art.strip().splitlines()]
    cols = len(lines[0])
    assert all(len(ln) == cols for ln in lines)
    board = [E if ch == "." else ord(ch) - ord("A") for ln in lines for ch in ln]
    return board, len(lines), cols


def at(cols: int, r: int, c: int) -> int:
    return r * cols + c


# (name, board, a, b) with a and b as (row, column).
CONNECT_CASES: list[tuple[str, str, tuple[int, int], tuple[int, int]]] = [
    ("direct: neighbours in a row", """
        AA..
        BCDE
        """, (0, 0), (0, 1)),
    ("direct: across a gap in a row", """
        A..A
        BCDE
        """, (0, 0), (0, 3)),
    ("direct: across a gap in a column", """
        BAC
        D.E
        FAG
        """, (0, 1), (2, 1)),
    ("one turn", """
        BCDE
        FA..
        GHIA
        """, (1, 1), (2, 3)),
    ("one turn: both corners open, the corner in a's row wins", """
        BBBBB
        BA..B
        B...B
        B..AB
        BBBBB
        """, (1, 1), (3, 3)),
    ("one turn: only the corner in b's row is open", """
        BBBBB
        BACCB
        B.C.B
        B..AB
        BBBBB
        """, (1, 1), (3, 3)),
    ("two turns inside the board", """
        BBBBBB
        BA..CB
        BCC.CB
        BCC.AB
        BBBBBB
        """, (1, 1), (3, 4)),
    ("two turns around the top ring", """
        ACBA
        BCBC
        """, (0, 0), (0, 3)),
    ("two turns around the left ring", """
        AB
        CD
        AE
        """, (0, 0), (2, 0)),
    ("two turns around the bottom ring", """
        BCDE
        A.FA
        """, (1, 0), (1, 3)),
    ("two turns around the right ring", """
        BA
        CD
        EA
        """, (0, 1), (2, 1)),
    ("two turns: along the top row and down the right ring", """
        A...
        BCDE
        FGH.
        IJKA
        """, (0, 0), (3, 3)),
    ("two turns: the shortest of several rows", """
        ......
        .ACC..
        .CCCA.
        """, (1, 1), (2, 4)),
    ("two turns: equal rows above and below, the upper wins", """
        ......
        .ACCA.
        ......
        """, (1, 1), (1, 4)),
    ("two turns: a column beats a longer row", """
        C.C.C
        .AC.C
        .CC.C
        ...AC
        CCCCC
        """, (1, 1), (3, 3)),
    ("blocked in a row", """
        CDE
        ABA
        FGH
        """, (1, 0), (1, 2)),
    ("blocked: walled in", """
        BBBBB
        BABAB
        BBBBB
        """, (1, 1), (1, 3)),
    ("three turns needed", """
        BBBBB
        BA.BB
        BB..B
        BBBAB
        BBBBB
        """, (1, 1), (3, 3)),
    ("three turns needed: cross on a 2x2", """
        AB
        BA
        """, (0, 0), (1, 1)),
    ("different kinds", """
        AB..
        CDEF
        """, (0, 0), (0, 1)),
    ("the same cell", """
        AA..
        CDEF
        """, (0, 0), (0, 0)),
    ("an empty cell", """
        A...
        CDEA
        """, (0, 0), (0, 1)),
]

SHIFT_CASES = [
    """
    A.B.C.
    .D..E.
    F....G
    .HI.J.
    """,
    """
    AB.CDE
    ......
    F.GH.I
    JKLMNO
    """,
]

FIND_CASES = [
    """
    AB
    BA
    """,
    """
    ABCD
    DCBA
    """,
    """
    ABCA
    DEFG
    """,
    """
    AB.C
    CD.B
    .EAF
    """,
]


def random_board(rows: int, cols: int, kinds: int, holes: int, seed: int) -> list[int]:
    """The rows * cols tiles dealt as pairs of [kinds] kinds in turn, shuffled, then [holes] pairs emptied."""
    rng = random.Random(seed)
    deck = [k // 2 % kinds for k in range(rows * cols)]
    rng.shuffle(deck)
    for _ in range(holes):
        k = rng.choice(sorted({t for t in deck if t != E}))
        cells = [i for i, t in enumerate(deck) if t == k]
        for i in rng.sample(cells, 2):
            deck[i] = E
    return deck


def path(p: list[tuple[int, int]] | None) -> list[list[int]] | None:
    return None if p is None else [list(x) for x in p]


def build() -> dict[str, Any]:
    connect = []
    for name, art, (ra, ca), (rb, cb) in CONNECT_CASES:
        board, rows, cols = parse(art)
        a, b = at(cols, ra, ca), at(cols, rb, cb)
        connect.append({"name": name, "rows": rows, "cols": cols, "board": board, "a": a, "b": b,
                        "path": path(link.connect(board, rows, cols, a, b))})
    # Every same-kind pair (both orders) of a few half-cleared boards, for the tie-breaks no case above picked.
    boards = []
    for seed, (rows, cols, kinds, holes) in enumerate([(5, 6, 4, 6), (6, 8, 6, 10), (4, 10, 5, 5)]):
        board = random_board(rows, cols, kinds, holes, seed)
        pairs = [{"a": a, "b": b, "path": path(link.connect(board, rows, cols, a, b))}
                 for a in range(rows * cols) for b in range(rows * cols)
                 if a != b and board[a] != E and board[a] == board[b]]
        boards.append({"rows": rows, "cols": cols, "board": board, "pairs": pairs})
    shift = []
    for art in SHIFT_CASES:
        board, rows, cols = parse(art)
        for s in link.SHIFTS:
            shift.append({"rows": rows, "cols": cols, "board": board, "shift": s,
                          "out": link.apply_shift(board, rows, cols, s)})
    find = []
    for art in FIND_CASES:
        board, rows, cols = parse(art)
        p = link.find_pair(board, rows, cols)
        find.append({"rows": rows, "cols": cols, "board": board, "pair": None if p is None else list(p)})
    # Greedy play on a dealt board under each shift: each step's pair is find_pair's, then remove_pair's board.
    sequences = []
    for seed, s in enumerate(link.SHIFTS):
        rows, cols, kinds = 6, 8, 12
        board = random_board(rows, cols, kinds, 0, 100 + seed)
        steps = []
        cur = board
        while (p := link.find_pair(cur, rows, cols)) is not None:
            cur = link.remove_pair(cur, rows, cols, s, *p)
            steps.append({"a": p[0], "b": p[1], "board": cur})
        sequences.append({"rows": rows, "cols": cols, "shift": s, "board": board, "steps": steps})
    return {"connect": connect, "boards": boards, "shift": shift, "find": find, "sequences": sequences}


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(build(), ensure_ascii=False) + "\n", encoding="utf-8")
