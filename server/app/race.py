"""The dumpling race's rules (design §6), with no storage or clock: a race is fully determined by its setup and the
random stream it draws from, and its odds by the coins staked on it.

The track is a lap of `track` squares: square 0 is the start and square `track` the finish, the same corner of the
board. The five dumplings start together on square 0, in lanes drawn at random. Then each rolls a six-sided die for
the order: the higher face moves first, and those on the same face roll again among themselves until they part (see
opening()). The order holds for the whole race: each round all five move once in it. A move rolls a die and carries
every dumpling stacked on the mover along; on square 0 nobody is stacked, so a move from there carries nobody. The
finish must be reached exactly: a roll that would carry the group past it takes it to the finish and back by the
squares left over (bounce()). Landing on an occupied square past the start puts the movers on top; landing on the
boost or trip square moves the whole group once more. The race goes on, with no limit on rounds, until a group lands
on the finish; every dumpling is ranked by square, within a square the higher one ahead, and on square 0 by lane.

All five dumplings are alike, so every member has the same chance of each place. The odds start from it and move with
the coins staked: see odds_tenths().

The real race draws from StreamRng (SHA-256 of the seed), which anyone can recompute from the published seed.
"""
from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

# The most any selection pays, in tenths (×99.0).
MAX_ODDS_TENTHS = 990
# How many places each kind of bet covers: its chance for each of n alike members is places / n.
PLACES = {"win": 1, "top2": 2, "last": 1}
# The faces of the die rolled for the order (apart from the dice a move rolls).
ORDER_FACES = 6


# ---------------------------------------------------------------- randomness
class StreamRng:
    """Random numbers from a seed anyone can recompute: 32-bit words, big-endian, from the blocks
    SHA-256(seed || counter), counter an 8-byte big-endian integer from 0, each block giving 8 words in order."""

    def __init__(self, seed: bytes) -> None:
        self.seed = seed
        self.counter = 0
        self.words: list[int] = []
        self.at = 0

    def _word(self) -> int:
        if self.at == len(self.words):
            block = hashlib.sha256(self.seed + self.counter.to_bytes(8, "big")).digest()
            self.counter += 1
            self.words = list(struct.unpack(">8I", block))
            self.at = 0
        w = self.words[self.at]
        self.at += 1
        return w

    def below(self, n: int) -> int:
        """Uniform in [0, n): words at or above the largest multiple of n under 2^32 are skipped."""
        limit = (1 << 32) - (1 << 32) % n
        while True:
            w = self._word()
            if w < limit:
                return w % n


def seed_hash(seed: bytes) -> str:
    """The commitment published while bets are open: SHA-256 of the seed's bytes, in hex."""
    return hashlib.sha256(seed).hexdigest()


# ---------------------------------------------------------------- the rules
@dataclass(frozen=True)
class Rules:
    """The manifest's race rules (economy.park.race) in the form the race loop reads quickly. [members] are the
    manifest's character ids in manifest order, which is the order the random draws refer to."""
    members: tuple[str, ...]
    track: int
    dice: tuple[int, ...]
    square_range: tuple[int, int]
    boost: int
    trip: int

    @classmethod
    def of(cls, cfg: dict[str, Any], members: list[str] | tuple[str, ...]) -> "Rules":
        sq = cfg["squares"]
        return cls(members=tuple(members), track=int(cfg["track"]), dice=tuple(cfg["dice"]),
                   square_range=(int(sq["range"][0]), int(sq["range"][1])), boost=int(sq["boost"]),
                   trip=int(sq["trip"]))


def deal(rules: Rules, rng: Any) -> dict[str, Any]:
    """A race's setup: the boost and trip squares (two different ones)."""
    lo, hi = rules.square_range
    boost, trip = rng.sample(range(lo, hi + 1), 2)
    return {"boost": boost, "trip": trip}


def _shuffle(items: list[int], below: Any) -> None:
    """Fisher-Yates from the end, as random.shuffle draws: for i from len - 1 down to 1, swap i with below(i + 1)."""
    for i in range(len(items) - 1, 0, -1):
        j = below(i + 1)
        items[i], items[j] = items[j], items[i]


def opening(n: int, below: Any) -> tuple[list[int], list[list[tuple[int, int]]]]:
    """The order of play of [n] members (indices into the members): each rolls below(ORDER_FACES) + 1, the higher
    face first. Members sharing a face with another roll again, all of them in the same round even when they tie on
    different faces, but each is only compared within its own tie. Every round draws in member order, so round one
    is everyone, from the first member to the last. A member's rolls so far are its key, and the order is the keys
    from the highest down, compared face by face. Returns (order, rounds), each round its rolls [(member, face)] in
    the order drawn.

    Faces 6 6 3 3 1: the first four roll again; on 5 2 4 4 the last two roll once more."""
    keys: list[list[int]] = [[] for _ in range(n)]
    rounds: list[list[tuple[int, int]]] = []
    rolling = list(range(n))
    while rolling:
        got = [(d, below(ORDER_FACES) + 1) for d in rolling]
        for d, face in got:
            keys[d].append(face)
        rounds.append(got)
        rolling = [d for d in range(n) if any(e != d and keys[e] == keys[d] for e in range(n))]
    return sorted(range(n), key=lambda d: keys[d], reverse=True), rounds


def bounce(square: int, track: int) -> int:
    """Where a move that would end on [square] lands: past the finish it walks back from it by what is left over."""
    return 2 * track - square if square > track else max(0, square)


def run(rules: Rules, setup: dict[str, Any], rng: Any) -> dict[str, Any]:
    """Runs one race. Returns {ranking, start, order, rolls, moves}: ranking first to last; start the lanes on the
    start line, top lane first; order who moves first to last, every round; rolls the order's rounds of dice, each
    [{m, face}] in the order drawn; each move as described in PROTOCOL.md (团子赛跑).

    Draw order: the lanes (one shuffle), the order (opening()), then each move's die (below(len(dice)))."""
    members = rules.members
    below = rng.below
    dice = rules.dice
    nd = len(dice)
    track = rules.track
    squares = {setup["boost"]: rules.boost, setup["trip"]: rules.trip}
    square_kind = {setup["boost"]: "boost", setup["trip"]: "trip"}
    n = len(members)
    idx = list(range(n))

    start = idx[:]
    _shuffle(start, below)
    lane = {d: i for i, d in enumerate(start)}
    pos = [0] * n
    # Stacks bottom to top, on squares past the start only: square 0 holds everyone side by side.
    stack: dict[int, list[int]] = {}

    def height(d: int) -> int:
        # Higher is further ahead: up a stack, or on square 0 towards the top lane.
        return stack[pos[d]].index(d) if pos[d] else -lane[d]

    order, rounds = opening(n, below)
    rolls = [[{"m": members[d], "face": face} for d, face in got] for got in rounds]
    moves: list[dict[str, Any]] = []
    while True:
        for d in order:
            roll = dice[below(nd)]
            p = pos[d]
            if p:
                s = stack[p]
                k = s.index(d)
                group = s[k:]
                if k:
                    stack[p] = s[:k]
                else:
                    del stack[p]
            else:
                group = [d]
            land = bounce(p + roll, track)
            q = land
            if q in squares:
                q = bounce(q + squares[q], track)
            if q:
                stack.setdefault(q, []).extend(group)
            for g in group:
                pos[g] = q
            step: dict[str, Any] = {"m": members[d], "dice": [roll], "steps": roll, "from": p, "to": land}
            if len(group) > 1:
                step["carry"] = [members[g] for g in group[1:]]
            if land in square_kind:
                step["square"] = square_kind[land]
                step["end"] = q
            moves.append(step)
            if q == track:
                ranked = sorted(idx, key=lambda x: (pos[x], height(x)), reverse=True)
                return {"ranking": [members[x] for x in ranked], "start": [members[x] for x in start],
                        "order": [members[x] for x in order], "rolls": rolls, "moves": moves}


def run_seed(rules: Rules, setup: dict[str, Any], seed: bytes) -> dict[str, Any]:
    """The real race of [seed]."""
    return run(rules, setup, StreamRng(seed))


# ---------------------------------------------------------------- odds
def odds_tenths(cfg: dict[str, Any], kind: str, members: tuple[str, ...] | list[str],
                stakes: dict[str, int]) -> dict[str, int]:
    """The odds of each member for [kind], in tenths, given the coins [stakes] on each member for that kind.

    With p = places / n for every member: share = (stake + depth × p / Σp) / (all stakes + depth), and the odds
    payout / (share × Σp), rounded down to a tenth, at least minOdds and at most MAX_ODDS_TENTHS. Exact arithmetic,
    so the rounding never slips on a float."""
    n = len(members)
    places = PLACES[kind]
    depth = int(cfg["depth"])
    payout = Fraction(str(cfg["payout"]))
    total = sum(stakes.get(m, 0) for m in members)
    low = round(Fraction(str(cfg["minOdds"])) * 10)
    out: dict[str, int] = {}
    for m in members:
        # share × Σp = (n × stake + depth) × places / (n × (total + depth))
        t = math.floor(10 * payout * n * (total + depth) / ((n * stakes.get(m, 0) + depth) * places))
        out[m] = max(low, min(MAX_ODDS_TENTHS, t))
    return out


def odds(cfg: dict[str, Any], members: tuple[str, ...] | list[str],
         stakes: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """The odds of every (kind, member), in tenths, from the coins staked: stakes[kind][member]."""
    return {kind: odds_tenths(cfg, kind, members, stakes.get(kind, {})) for kind in cfg["kinds"]}
