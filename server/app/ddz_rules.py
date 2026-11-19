"""Dou dizhu (斗地主) hands: what a set of cards is, whether it beats another, and what to play for a seat.

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
ACE, TWO = 14, 15
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


# ------------------------------------------------------------- playing for a seat
# A seat on autopilot, or whose member is away or let the time run out, is played for by choose(): plain rules, no
# look-ahead. Four of a rank and the rocket are kept whole: played, with what goes along, or broken up only when an
# opponent is down to DANGER cards or fewer, or when the play ends the hand or leaves it one play from the end.
DANGER = 5
# Per kind: the cards taken from each rank of its run, the kickers that go along per rank of the run, and whether
# those are single cards (1) or pairs (2).
_SHAPES = {
    "solo": (1, 0, 0), "pair": (2, 0, 0), "trio": (3, 0, 0), "trio1": (3, 1, 1), "trio2": (3, 1, 2),
    "straight": (1, 0, 0), "pairs": (2, 0, 0), "plane": (3, 0, 0), "plane1": (3, 1, 1), "plane2": (3, 1, 2),
    "four2": (4, 2, 1), "four22": (4, 2, 2),
}


class _Hold:
    """The cards of a hand by rank, and which ranks are kept whole: four of a rank, and both jokers."""

    def __init__(self, hand: Iterable[int]) -> None:
        self.cards: dict[int, list[int]] = {}
        for c in sorted(hand):
            self.cards.setdefault(rank(c), []).append(c)
        self.count = {r: len(cs) for r, cs in self.cards.items()}
        self.kept = {r for r, n in self.count.items() if n == 4}
        if SMALL_JOKER in self.count and BIG_JOKER in self.count:
            self.kept |= {SMALL_JOKER, BIG_JOKER}

    def take(self, taken: dict[int, int]) -> list[int]:
        return sorted(c for r, n in taken.items() for c in self.cards[r][:n])

    def cost(self, taken: dict[int, int]) -> tuple[int, int]:
        """Ranks kept whole that [taken] spends, and other ranks it splits or plays 2s or a joker from (each counts
        once), so a low pair is split before a 2 or a lone joker goes."""
        spent = sum(1 for r in taken if r in self.kept)
        split = sum(1 for r, n in taken.items() if r not in self.kept and (n < self.count[r] or r >= TWO))
        return spent, split

    def kickers(self, taken: dict[int, int], n: int, width: int) -> dict[int, int] | None:
        """[taken] with the [n] cheapest singles (width 1) or pairs (width 2) added from other ranks; None when the
        hand has too few."""
        units = []
        for r, have in self.count.items():
            if r in taken or (width == 2 and r >= SMALL_JOKER):
                continue
            units += [r] * (have // width)
        # Ranks kept whole come last, then 2s and jokers, then ranks the kicker would split; low ranks first.
        units.sort(key=lambda r: (r in self.kept, r >= TWO, self.count[r] > width, r))
        if len(units) < n:
            return None
        out = dict(taken)
        for r in units[:n]:
            out[r] = out.get(r, 0) + width
        return out


def _follows(hold: _Hold, last: Hand) -> list[tuple[tuple[int, int, int], list[int]]]:
    """Plays of [last]'s kind and size from [hold] that rank above it, with their costs; bombs and the rocket not
    included."""
    if last.kind not in _SHAPES:
        return []
    per, kick, width = _SHAPES[last.kind]
    length = last.size
    out = []
    for top in range(last.main + 1, BIG_JOKER + 1):
        run = range(top - length + 1, top + 1)
        if length > 1 and top > ACE or any(hold.count.get(r, 0) < per for r in run):
            continue
        taken = {r: per for r in run}
        if kick:
            taken = hold.kickers(taken, kick * length, width)
            if taken is None:
                continue
        out.append((hold.cost(taken) + (top,), hold.take(taken)))
    return out


def choose(hand: Iterable[int], last: Iterable[int] | None, *, partner_led: bool = False,
           danger: bool = False) -> list[int]:
    """The cards to play from [hand] on [last] (None to lead); [] passes. [partner_led]: [last] is the other farmer's.
    [danger]: an opponent has DANGER cards or fewer."""
    hand = sorted(hand)
    whole = bool(classify(hand))
    if last is None:
        return hand if whole else _lead(_Hold(hand))
    last = sorted(last)
    if whole and beats(hand, last):
        return hand
    if partner_led:
        return []
    hold = _Hold(hand)
    plays = sorted((p for h in classify(last) for p in _follows(hold, h)), key=lambda p: p[0])
    plays = [(cost, cards) for cost, cards in plays if beats(cards, last)]
    for cost, cards in plays:
        if cost[0] == 0:
            return cards
    # What is left spends a bomb, a four or the rocket: the lowest bomb, the rocket, then plays that break one up.
    spend = [hold.cards[r] for r in sorted(r for r, n in hold.count.items() if n == 4)]
    if hold.kept >= {SMALL_JOKER, BIG_JOKER}:
        spend.append(hold.cards[SMALL_JOKER] + hold.cards[BIG_JOKER])
    spend += [cards for _, cards in plays]
    for cards in spend:
        if not beats(cards, last):
            continue
        gone = set(cards)
        if danger or classify([c for c in hand if c not in gone]) or len(gone) == len(hand):
            return sorted(cards)
    return []


def _lead(hold: _Hold) -> list[int]:
    """A lead for a hand that is not one play: the lowest rank not kept whole, as a run of singles when one starts
    there, else with the rest of its rank."""
    free = sorted(r for r in hold.count if r not in hold.kept)
    if not free:
        # Only bombs and the rocket: the lowest bomb, else the rocket.
        fours = sorted(r for r, n in hold.count.items() if n == 4)
        return hold.cards[fours[0]] if fours else hold.cards[SMALL_JOKER] + hold.cards[BIG_JOKER]
    low = free[0]
    top = low
    while top + 1 <= ACE and hold.count.get(top + 1) == 1:
        top += 1
    if hold.count[low] == 1 and top <= ACE and top - low + 1 >= 5:
        return hold.take({r: 1 for r in range(low, top + 1)})
    taken = {low: hold.count[low]}
    if hold.count[low] == 3:
        # A trio takes the lowest single below the 2s along, else the lowest such pair, else goes alone.
        for width in (1, 2):
            spare = sorted(r for r, n in hold.count.items()
                           if n == width and r != low and r < TWO and r not in hold.kept)
            if spare:
                taken[spare[0]] = width
                break
    return hold.take(taken)
