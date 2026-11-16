"""Dou dizhu (斗地主) hands: what a set of cards is and whether it beats another.

The client has the same rules in client/src/ddz/rules.ts; both are checked against one fixture
(client/src/ddz/rules.fixture.json), so a play the client lets through is one the server takes.

Cards are 0..53: card // 4 + 3 is the rank for 0..51 (3..10, J=11, Q=12, K=13, A=14, 2=15) and card % 4 the suit
(0 spade, 1 heart, 2 club, 3 diamond); 52 is the small joker (rank 16), 53 the big one (17). Suits never matter.

The hands follow the 37 kinds of onestraw/doudizhu (MIT), read as rules rather than listed out:

- solo, pair, trio, bomb (four of a rank), rocket (both jokers);
- trio1 (a trio and one other card), trio2 (a trio and a pair);
- straight (5 or more ranks in a row), pairs (3 or more pairs in a row), plane (2 or more trios in a row); none of
  the three reaches past the ace;
- plane1 (2 to 5 trios in a row and as many other cards), plane2 (2 to 4 trios in a row and as many pairs);
- four2 (four of a rank and two other cards), four22 (four of a rank and two pairs).

Cards that go along with trios or fours are never of the ranks they go with, and "pairs" that go along are never
jokers; two pairs that go along may be of one rank. Cards that can be read two ways are both: 3333-4444 is four22
led by the threes and four22 led by the fours, 333-444-555-666 a plane of four and a plane1 of three.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, NamedTuple

SMALL_JOKER, BIG_JOKER = 16, 17
ACE = 14
DECK = tuple(range(54))


class Hand(NamedTuple):
    kind: str
    # Trios, pairs or single cards in the run; 1 for hands without one.
    size: int
    # The rank that is compared: the hand's own, or the top of its run.
    main: int


def rank(card: int) -> int:
    return card // 4 + 3 if card < 52 else card - 36


def ranks(cards: Iterable[int]) -> list[int]:
    return sorted(rank(c) for c in cards)


def _runs(have: list[int], size: int) -> list[int]:
    """Top ranks of the runs of [size] ranks in a row, none past the ace, within the sorted ranks [have]."""
    pool = set(r for r in have if r <= ACE)
    return [top for top in sorted(pool) if all(top - i in pool for i in range(size))]


def classify(cards: Iterable[int]) -> list[Hand]:
    """Every way to read [cards] as one hand; empty when they are none."""
    rs = ranks(cards)
    n = len(rs)
    if n == 0:
        return []
    count = Counter(rs)
    by = {k: sorted(r for r, c in count.items() if c == k) for k in (1, 2, 3, 4)}
    distinct = len(count)
    out: list[Hand] = []
    top = rs[-1]

    if n == 1:
        return [Hand("solo", 1, top)]
    if n == 2:
        if rs == [SMALL_JOKER, BIG_JOKER]:
            return [Hand("rocket", 1, BIG_JOKER)]
        return [Hand("pair", 1, top)] if distinct == 1 else []
    if n == 3:
        return [Hand("trio", 1, top)] if distinct == 1 else []
    if n == 4 and distinct == 1:
        return [Hand("bomb", 1, top)]

    whole_run = top <= ACE and top - rs[0] == distinct - 1
    if distinct == n and n >= 5 and whole_run:
        out.append(Hand("straight", n, top))
    if len(by[2]) == distinct and distinct >= 3 and whole_run:
        out.append(Hand("pairs", distinct, top))
    if len(by[3]) == distinct and distinct >= 2 and whole_run:
        out.append(Hand("plane", distinct, top))

    # A trio, or trios in a row, with one other card each: 4 cards a trio.
    if n % 4 == 0 and 1 <= n // 4 <= 5:
        size = n // 4
        for t in ([r for r in by[3]] if size == 1 else _runs(by[3], size)):
            out.append(Hand("trio1" if size == 1 else "plane1", size, t))
    # The same with a pair each: 5 cards a trio. What is left must be whole pairs, none of jokers.
    if n % 5 == 0 and 1 <= n // 5 <= 4:
        size = n // 5
        for t in ([r for r in by[3]] if size == 1 else _runs(by[3], size)):
            run = set(range(t - size + 1, t + 1))
            rest = {r: c for r, c in count.items() if r not in run}
            if all(c in (2, 4) and r < SMALL_JOKER for r, c in rest.items()):
                out.append(Hand("trio2" if size == 1 else "plane2", size, t))
    if n == 6:
        out.extend(Hand("four2", 1, r) for r in by[4])
    if n == 8:
        for r in by[4]:
            rest = {x: c for x, c in count.items() if x != r}
            if all(c in (2, 4) and x < SMALL_JOKER for x, c in rest.items()):
                out.append(Hand("four22", 1, r))
    return out


def hand_beats(a: Hand, b: Hand) -> bool:
    if a.kind == "rocket":
        return True
    if b.kind == "rocket":
        return False
    if a.kind == "bomb":
        return b.kind != "bomb" or a.main > b.main
    return a.kind == b.kind and a.size == b.size and a.main > b.main


def beats(cards: Iterable[int], last: Iterable[int]) -> bool:
    """Whether [cards] may be played on [last]: some reading of the one beats some reading of the other."""
    mine, theirs = classify(cards), classify(last)
    return any(hand_beats(a, b) for a in mine for b in theirs)


def bombs(cards: Iterable[int]) -> int:
    """1 for a bomb or the rocket, which double the stake; else 0."""
    return int(any(h.kind in ("bomb", "rocket") for h in classify(cards)))
