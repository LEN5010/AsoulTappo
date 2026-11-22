"""Board rules of the park link game (连连看, Shisen-Sho rules; docs/design/park-link.md sections 3 and 4).

A board is a flat list of rows * cols kinds, index r * cols + c, with EMPTY for a removed tile. Two tiles of one kind
link when a line of at most three horizontal and vertical segments (two turns) joins them over empty cells. The ring
of cells just outside the board (row -1 and rows, column -1 and cols) is always empty, so lines can run around it.

client/src/panel/park/link.ts holds the same rules for drawing and hints; both are checked against
client/src/panel/park/link.fixture.json (tests/gen_link_fixture.py). Generation and shuffling run on the server only.

Path search follows KDE KShisen src/board.cpp (findPath, findSimplePath; GPL-2.0-or-later), with candidates
enumerated in a fixed order so both clients draw the same line. The greedy solvability check and the redistribution
of unsolved tiles follow KShisen's isSolvable and newGame. Reverse placement follows ALGO_REVERSE in shisen-seki
src/board.c (MIT), without its escape that accepts an unlinked pair when the first tile is walled in."""
from __future__ import annotations

import time
from typing import Sequence

from .cards import Rng

EMPTY = -1
SHIFTS = ("none", "down", "left", "center")

Pos = tuple[int, int]

# Generation limits (section 4). The attempt caps decide in practice; the clock bounds a busy core or a large board.
REVERSE_TRIES = 40
REVERSE_RESTARTS = 50
SOLVE_TRIES = 60
BUDGET_S = 0.04
SHUFFLE_TRIES = 30


def _below(rng: Rng, n: int) -> int:
    """An integer in [0, n) from a generator that only has random(), as scratch._take draws."""
    return min(int(rng.random() * n), n - 1)


def _free(board: Sequence[int], rows: int, cols: int, r: int, c: int) -> bool:
    return r < 0 or r >= rows or c < 0 or c >= cols or board[r * cols + c] == EMPTY


def _row_clear(board: Sequence[int], rows: int, cols: int, r: int, c1: int, c2: int) -> bool:
    """Every cell of row r strictly between columns c1 and c2 is empty."""
    if r < 0 or r >= rows:
        return True
    lo, hi = (c1, c2) if c1 < c2 else (c2, c1)
    base = r * cols
    for c in range(max(lo + 1, 0), min(hi, cols)):
        if board[base + c] != EMPTY:
            return False
    return True


def _col_clear(board: Sequence[int], rows: int, cols: int, c: int, r1: int, r2: int) -> bool:
    """Every cell of column c strictly between rows r1 and r2 is empty."""
    if c < 0 or c >= cols:
        return True
    lo, hi = (r1, r2) if r1 < r2 else (r2, r1)
    for r in range(max(lo + 1, 0), min(hi, rows)):
        if board[r * cols + c] != EMPTY:
            return False
    return True


def _route(board: Sequence[int], rows: int, cols: int, a: int, b: int, best: bool) -> list[Pos] | None:
    """The line between cells a and b, whatever they hold: its corners from a to b, or None.

    Candidates in order: the straight line; one turn at (ra, cb), then at (rb, ca); two turns through each row R from
    -1 to rows (a goes vertically to row R, along it, then vertically to b), then through each column C from -1 to
    cols. With [best] the line with the fewest turns, then the shortest total length, wins, the first in this order on
    a tie; without it, the first line found, for callers that only ask whether one exists."""
    r1, c1 = divmod(a, cols)
    r2, c2 = divmod(b, cols)
    if r1 == r2 and _row_clear(board, rows, cols, r1, c1, c2):
        return [(r1, c1), (r2, c2)]
    if c1 == c2 and _col_clear(board, rows, cols, c1, r1, r2):
        return [(r1, c1), (r2, c2)]
    if r1 != r2 and c1 != c2:
        if (_free(board, rows, cols, r1, c2) and _row_clear(board, rows, cols, r1, c1, c2)
                and _col_clear(board, rows, cols, c2, r1, r2)):
            return [(r1, c1), (r1, c2), (r2, c2)]
        if (_free(board, rows, cols, r2, c1) and _col_clear(board, rows, cols, c1, r1, r2)
                and _row_clear(board, rows, cols, r2, c1, c2)):
            return [(r1, c1), (r2, c1), (r2, c2)]
    found: list[Pos] | None = None
    length = 0
    if c1 != c2:
        # The run of empty cells above and below each end bounds the rows a line can turn in.
        lo1, hi1 = r1, r1
        while lo1 > -1 and _free(board, rows, cols, lo1 - 1, c1):
            lo1 -= 1
        while hi1 < rows and _free(board, rows, cols, hi1 + 1, c1):
            hi1 += 1
        lo2, hi2 = r2, r2
        while lo2 > -1 and _free(board, rows, cols, lo2 - 1, c2):
            lo2 -= 1
        while hi2 < rows and _free(board, rows, cols, hi2 + 1, c2):
            hi2 += 1
        for r in range(max(lo1, lo2), min(hi1, hi2) + 1):
            if r == r1 or r == r2 or not _row_clear(board, rows, cols, r, c1, c2):
                continue
            n = abs(r - r1) + abs(c1 - c2) + abs(r - r2)
            if found is None or n < length:
                found, length = [(r1, c1), (r, c1), (r, c2), (r2, c2)], n
                if not best:
                    return found
    if r1 != r2:
        lo1, hi1 = c1, c1
        while lo1 > -1 and _free(board, rows, cols, r1, lo1 - 1):
            lo1 -= 1
        while hi1 < cols and _free(board, rows, cols, r1, hi1 + 1):
            hi1 += 1
        lo2, hi2 = c2, c2
        while lo2 > -1 and _free(board, rows, cols, r2, lo2 - 1):
            lo2 -= 1
        while hi2 < cols and _free(board, rows, cols, r2, hi2 + 1):
            hi2 += 1
        for c in range(max(lo1, lo2), min(hi1, hi2) + 1):
            if c == c1 or c == c2 or not _col_clear(board, rows, cols, c, r1, r2):
                continue
            n = abs(c - c1) + abs(r1 - r2) + abs(c - c2)
            if found is None or n < length:
                found, length = [(r1, c1), (r1, c), (r2, c), (r2, c2)], n
                if not best:
                    return found
    return found


def _pair_ok(board: Sequence[int], a: int, b: int) -> bool:
    n = len(board)
    return (type(a) is int and type(b) is int and a != b and 0 <= a < n and 0 <= b < n
            and board[a] != EMPTY and board[a] == board[b])


def connect(board: Sequence[int], rows: int, cols: int, a: int, b: int) -> list[Pos] | None:
    """The corners of the line joining tiles a and b, both ends included and ring cells as out-of-range coordinates;
    None when they are the same cell, either is empty, the kinds differ or no line of at most two turns exists. The
    line has the fewest turns, then the shortest length (see _route for the order that breaks ties)."""
    if not _pair_ok(board, a, b):
        return None
    return _route(board, rows, cols, a, b, True)


def linked(board: Sequence[int], rows: int, cols: int, a: int, b: int) -> bool:
    """Whether connect would answer a line, without picking the best one."""
    return _pair_ok(board, a, b) and _route(board, rows, cols, a, b, False) is not None


def apply_shift(board: Sequence[int], rows: int, cols: int, shift: str) -> list[int]:
    """A new board with the tiles moved by [shift], each line keeping its order: none leaves them, down drops each
    column to the bottom, left packs each row to the left, center packs each half row toward the middle line (the left
    half, c < cols / 2, to its right end; the right half to its left end). The input is not changed."""
    out = list(board)
    if shift == "none":
        return out
    if shift == "down":
        for c in range(cols):
            tiles = [board[r * cols + c] for r in range(rows) if board[r * cols + c] != EMPTY]
            pad = rows - len(tiles)
            for r in range(rows):
                out[r * cols + c] = EMPTY if r < pad else tiles[r - pad]
        return out
    if shift == "left":
        for r in range(rows):
            line = board[r * cols:(r + 1) * cols]
            tiles = [t for t in line if t != EMPTY]
            out[r * cols:(r + 1) * cols] = tiles + [EMPTY] * (cols - len(tiles))
        return out
    if shift == "center":
        if cols % 2:
            raise ValueError("center needs an even number of columns")
        half = cols // 2
        for r in range(rows):
            left = [t for t in board[r * cols:r * cols + half] if t != EMPTY]
            right = [t for t in board[r * cols + half:(r + 1) * cols] if t != EMPTY]
            out[r * cols:(r + 1) * cols] = ([EMPTY] * (half - len(left)) + left
                                            + right + [EMPTY] * (half - len(right)))
        return out
    raise ValueError(f"unknown shift {shift!r}")


def remove_pair(board: Sequence[int], rows: int, cols: int, shift: str, a: int, b: int) -> list[int]:
    """A new board with cells a and b emptied, then shifted. It does not check the pair; the input is not changed."""
    out = list(board)
    out[a] = EMPTY
    out[b] = EMPTY
    return apply_shift(out, rows, cols, shift)


def _by_kind(board: Sequence[int]) -> dict[int, list[int]]:
    cells: dict[int, list[int]] = {}
    for i, t in enumerate(board):
        if t != EMPTY:
            cells.setdefault(t, []).append(i)
    return cells


def find_pair(board: Sequence[int], rows: int, cols: int) -> tuple[int, int] | None:
    """The first pair of tiles that link, scanning a from the smallest index and b from a + 1 up; None if none do."""
    cells = _by_kind(board)
    for a, t in enumerate(board):
        if t == EMPTY:
            continue
        for b in cells[t]:
            if b > a and _route(board, rows, cols, a, b, False) is not None:
                return a, b
    return None


def _greedy(board: Sequence[int], rows: int, cols: int, shift: str) -> list[int]:
    """Removes the first linked pair until none is left, as KShisen's isSolvable; the board that remains."""
    cur = list(board)
    while True:
        p = find_pair(cur, rows, cols)
        if p is None:
            return cur
        cur = remove_pair(cur, rows, cols, shift, *p)


def solvable(board: Sequence[int], rows: int, cols: int, shift: str) -> bool:
    """Whether greedy play (always the pair find_pair gives, with the shift applied) clears the board. A False can
    still be a board some other order clears."""
    return all(t == EMPTY for t in _greedy(board, rows, cols, shift))


def _deck(cells: int, kinds: int) -> list[int]:
    if cells != kinds * 4:
        raise ValueError("rows * cols must be kinds * 4")
    return [k for k in range(kinds) for _ in range(4)]


def _odd_pocket(board: Sequence[int], rows: int, cols: int) -> bool:
    """Whether some group of empty cells, joined side by side and away from the board's edge, has an odd size. Such a
    group can never be filled by pairs (a line reaches it only through its own cells), so reverse placement avoids
    making one instead of finding out at the end and starting over."""
    seen = [False] * len(board)
    for s in range(len(board)):
        if board[s] != EMPTY or seen[s]:
            continue
        seen[s] = True
        stack = [s]
        size = 0
        edge = False
        while stack:
            i = stack.pop()
            size += 1
            r, c = divmod(i, cols)
            if r == 0 or c == 0 or r == rows - 1 or c == cols - 1:
                edge = True
            for j, ok in ((i - cols, r > 0), (i + cols, r < rows - 1), (i - 1, c > 0), (i + 1, c < cols - 1)):
                if ok and not seen[j] and board[j] == EMPTY:
                    seen[j] = True
                    stack.append(j)
        if not edge and size % 2:
            return True
    return False


def _reverse(rows: int, cols: int, kinds: int, rng: Rng,
             until: float | None = None) -> tuple[list[int], list[tuple[int, int]]] | None:
    """A full board placed pair by pair from an empty one, each pair linked when it is placed, so removing the pairs
    in the reverse order clears it under shift none; the board and the pairs in placement order. A placement that
    leaves an odd group of enclosed empty cells is tried elsewhere (see _odd_pocket); a pair that finds no place in
    REVERSE_TRIES first tiles starts the board over. None after REVERSE_RESTARTS restarts or past [until]
    (perf_counter seconds)."""
    n = rows * cols
    _deck(n, kinds)
    for _ in range(REVERSE_RESTARTS + 1):
        # Each kind is two pairs.
        order = [k for k in range(kinds) for _ in range(2)]
        for i in range(len(order) - 1, 0, -1):
            j = _below(rng, i + 1)
            order[i], order[j] = order[j], order[i]
        board = [EMPTY] * n
        pairs: list[tuple[int, int]] = []
        for k in order:
            empty = [i for i in range(n) if board[i] == EMPTY]
            placed = False
            for _ in range(REVERSE_TRIES):
                a = empty[_below(rng, len(empty))]
                board[a] = k
                # Trying the other empty cells in random order picks uniformly among the cells that would do.
                others = [b for b in empty if b != a]
                for i in range(len(others) - 1, -1, -1):
                    j = _below(rng, i + 1)
                    others[i], others[j] = others[j], others[i]
                    b = others[i]
                    if _route(board, rows, cols, a, b, False) is None:
                        continue
                    board[b] = k
                    if not _odd_pocket(board, rows, cols):
                        pairs.append((a, b))
                        placed = True
                        break
                    board[b] = EMPTY
                if placed:
                    break
                board[a] = EMPTY
            if not placed or (until is not None and time.perf_counter() > until):
                break
        else:
            return board, pairs
        if until is not None and time.perf_counter() > until:
            return None
    return None


def generate(rows: int, cols: int, kinds: int, shift: str, rng: Rng) -> list[int]:
    """A full board of [kinds] kinds, four tiles each. Under shift none it is placed in reverse and always solvable.
    Under the other shifts, or when reverse placement runs out of restarts or time, it is dealt at random and the tiles
    greedy play leaves are redistributed over their own cells until greedy play clears it (KShisen newGame); past the
    attempt cap or the time budget (BUDGET_S for the whole call) the last deal is kept, made to hold at least one
    linked pair."""
    if shift not in SHIFTS:
        raise ValueError(f"unknown shift {shift!r}")
    until = time.perf_counter() + BUDGET_S
    if shift == "none":
        placed = _reverse(rows, cols, kinds, rng, until)
        if placed is not None:
            return placed[0]
    n = rows * cols
    board = _deck(n, kinds)
    for i in range(n - 1, 0, -1):
        j = _below(rng, i + 1)
        board[i], board[j] = board[j], board[i]
    for _ in range(SOLVE_TRIES):
        # Play on tile ids (each tile's cell in [board]) so the leftovers name the cells they came from.
        ids = _greedy_ids(board, rows, cols, shift, until)
        if ids is None:
            break
        left = [t for t in ids if t != EMPTY]
        if not left:
            return board
        if time.perf_counter() > until:
            break
        kinds_left = [board[i] for i in left]
        for i in range(len(kinds_left) - 1, 0, -1):
            j = _below(rng, i + 1)
            kinds_left[i], kinds_left[j] = kinds_left[j], kinds_left[i]
        for i, k in zip(left, kinds_left):
            board[i] = k
    if find_pair(board, rows, cols) is None:
        return shuffle(board, rows, cols, rng)
    return board


def _greedy_ids(board: Sequence[int], rows: int, cols: int, shift: str, until: float) -> list[int] | None:
    """_greedy over a board of tile ids: the ids (original cells) greedy play leaves on the board, and EMPTY; None when
    the clock passes [until] (perf_counter seconds) before greedy play ends."""
    ids = [i if t != EMPTY else EMPTY for i, t in enumerate(board)]
    kind = list(board)
    while True:
        p = find_pair(kind, rows, cols)
        if p is None:
            return ids
        kind = remove_pair(kind, rows, cols, shift, *p)
        ids = remove_pair(ids, rows, cols, shift, *p)
        if time.perf_counter() > until:
            return None


def shuffle(board: Sequence[int], rows: int, cols: int, rng: Rng) -> list[int]:
    """A new board with the kinds of the tiles permuted over the same cells, holding at least one linked pair when two
    or more tiles are left. After a few random tries it makes one: two cells a line joins (neighbours first) get the
    same kind by a swap."""
    out = list(board)
    cells = [i for i, t in enumerate(out) if t != EMPTY]
    if len(cells) < 2:
        return out
    for _ in range(SHUFFLE_TRIES):
        kinds = [out[i] for i in cells]
        for i in range(len(kinds) - 1, 0, -1):
            j = _below(rng, i + 1)
            kinds[i], kinds[j] = kinds[j], kinds[i]
        for i, k in zip(cells, kinds):
            out[i] = k
        if find_pair(out, rows, cols) is not None:
            return out
    pair = _neighbours(out, rows, cols, cells) or _any_line(out, rows, cols, cells)
    if pair is None:  # Unreachable: some row or column holds two tiles, or two tiles meet over the top ring.
        return out
    a, b = pair
    if out[a] != out[b]:
        mate = next(i for i in cells if i != a and out[i] == out[a])
        out[b], out[mate] = out[mate], out[b]
    return out


def _neighbours(board: Sequence[int], rows: int, cols: int, cells: Sequence[int]) -> tuple[int, int] | None:
    for a in cells:
        r, c = divmod(a, cols)
        if c + 1 < cols and board[a + 1] != EMPTY:
            return a, a + 1
        if r + 1 < rows and board[a + cols] != EMPTY:
            return a, a + cols
    return None


def _any_line(board: Sequence[int], rows: int, cols: int, cells: Sequence[int]) -> tuple[int, int] | None:
    for x, a in enumerate(cells):
        for b in cells[x + 1:]:
            if _route(board, rows, cols, a, b, False) is not None:
                return a, b
    return None
