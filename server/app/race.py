"""The dumpling race's rules (design §6), with no storage or clock: a race is fully determined by its setup and the
random stream it draws from.

Five dumplings start stacked on square 0 in a random order. Each round all five move once in a random order. A move
rolls a die (or not, for a steady skill), adds the member's skill and the first few moves' mood, and carries every
dumpling stacked on the mover along. Landing on an occupied square puts the movers on top; landing on the boost or
trip square moves the whole group once more. The first group to reach the end finishes the race; every dumpling is
ranked by square, and within a square the higher one is ahead.

The rules follow docs/design/amusement-park-sims/raceodds.py draw for draw: with an rng that hands out the same
numbers, both give the same race. The real race draws from StreamRng (SHA-256 of the seed), which anyone can
recompute from the published seed; the odds sims draw from PyRng (Python's own generator, much faster).
"""
from __future__ import annotations

import hashlib
import random
import struct
from dataclasses import dataclass
from typing import Any

# Odds paid on a selection the sims never saw win, and the most any selection pays, in tenths (×99.0).
MAX_ODDS_TENTHS = 990


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

    def random(self) -> float:
        """Uniform in [0, 1) with 53 bits: the top 27 bits of one word, then the top 26 of the next."""
        a = self._word() >> 5
        b = self._word() >> 6
        return (a * 67108864 + b) / 9007199254740992.0


class PyRng:
    """Python's Mersenne Twister, drawing as random.randint, random.shuffle and random.random do."""

    def __init__(self, r: random.Random) -> None:
        self.below = r._randbelow  # type: ignore[attr-defined]
        self.random = r.random


def seed_hash(seed: bytes) -> str:
    """The commitment published while bets are open: SHA-256 of the seed's bytes, in hex."""
    return hashlib.sha256(seed).hexdigest()


# ---------------------------------------------------------------- the rules
@dataclass(frozen=True)
class Rules:
    """The manifest's race rules (economy.park.race) in the form the race loop reads quickly."""
    members: tuple[str, ...]
    track: int
    dice: tuple[int, ...]
    skills: dict[str, dict[str, Any]]
    moods: dict[str, dict[str, Any]]
    square_range: tuple[int, int]
    boost: int
    trip: int

    @classmethod
    def of(cls, cfg: dict[str, Any]) -> "Rules":
        sq = cfg["squares"]
        return cls(members=tuple(cfg["skills"]), track=int(cfg["track"]), dice=tuple(cfg["dice"]),
                   skills=dict(cfg["skills"]), moods={m["id"]: m for m in cfg["moods"]},
                   square_range=(int(sq["range"][0]), int(sq["range"][1])), boost=int(sq["boost"]),
                   trip=int(sq["trip"]))


def deal(rules: Rules, rng: Any) -> dict[str, Any]:
    """A race's setup: the moods dealt one to each member, and the boost and trip squares (two different ones)."""
    moods = list(rules.moods)
    rng.shuffle(moods)
    lo, hi = rules.square_range
    boost, trip = rng.sample(range(lo, hi + 1), 2)
    return {"moods": dict(zip(rules.members, moods)), "boost": boost, "trip": trip}


def run(rules: Rules, setup: dict[str, Any], rng: Any, record: bool = True) -> dict[str, Any]:
    """Runs one race. Returns {ranking, start, moves} (moves only when [record]): ranking first to last; start the
    starting stack, bottom to top; each move as described in PROTOCOL.md (团子赛跑)."""
    members = rules.members
    below, rand = rng.below, rng.random
    dice = rules.dice
    nd = len(dice)
    track = rules.track
    squares = {setup["boost"]: rules.boost, setup["trip"]: rules.trip}
    square_kind = {setup["boost"]: "boost", setup["trip"]: "trip"}
    skill = [rules.skills[m] for m in members]
    kinds = [s["kind"] for s in skill]
    mood_delta = []
    mood_moves = []
    for m in members:
        mood = rules.moods[setup["moods"][m]]
        mood_delta.append(int(mood["delta"]))
        mood_moves.append(int(mood["moves"]) if mood["delta"] else 0)
    n = len(members)
    idx = list(range(n))

    start = idx[:]
    # random.shuffle, draw for draw.
    for i in range(n - 1, 0, -1):
        j = below(i + 1)
        start[i], start[j] = start[j], start[i]
    pos = [0] * n
    stack: dict[int, list[int]] = {0: start[:]}
    used = [0] * n
    snack = [0] * n  # squares a snack adds to the member's next move
    last = -1  # who was last after the latest move (none before the first)
    moves: list[dict[str, Any]] = []
    while True:
        order = idx[:]
        for i in range(n - 1, 0, -1):
            j = below(i + 1)
            order[i], order[j] = order[j], order[i]
        for d in order:
            sk = skill[d]
            kind = kinds[d]
            rolled: list[int] = []
            add: list[list[Any]] = []
            earned = False
            if kind == "steady":
                roll = int(sk["steps"])
            else:
                roll = dice[below(nd)]
                rolled.append(roll)
                if kind == "reroll" and roll == sk["on"] and rand() < sk["chance"]:
                    roll = dice[below(nd)]
                    rolled.append(roll)
                elif kind == "snack":
                    if snack[d]:
                        roll += snack[d]
                        add.append(["snack", snack[d]])
                        snack[d] = 0
                    elif roll == sk["on"] and rand() < sk["chance"]:
                        snack[d] = int(sk["bonus"])
                        earned = True
                elif kind == "dash" and roll == sk["on"] and rand() < sk["chance"]:
                    roll += int(sk["bonus"])
                    add.append(["dash", int(sk["bonus"])])
            if kind == "catchup" and last == d:
                roll += int(sk["bonus"])
                add.append(["catchup", int(sk["bonus"])])
            if used[d] < mood_moves[d]:
                before = roll
                roll = max(1, roll + mood_delta[d])
                used[d] += 1
                add.append(["mood", roll - before])
            p = pos[d]
            s = stack[p]
            k = s.index(d)
            group = s[k:]
            if k:
                stack[p] = s[:k]
            else:
                del stack[p]
            land = p + roll
            q = land
            if q in squares:
                q = max(0, q + squares[q])
            stack.setdefault(q, []).extend(group)
            for g in group:
                pos[g] = q
            if record:
                step: dict[str, Any] = {"m": members[d], "dice": rolled, "steps": roll, "from": p,
                                        "to": min(land, track)}
                if add:
                    step["add"] = add
                if earned:
                    step["snack"] = snack[d]
                if len(group) > 1:
                    step["carry"] = [members[g] for g in group[1:]]
                if land in square_kind:
                    step["square"] = square_kind[land]
                    step["end"] = q
                moves.append(step)
            if q >= track:
                ranked = sorted(idx, key=lambda x: (pos[x], stack[pos[x]].index(x)), reverse=True)
                out: dict[str, Any] = {"ranking": [members[x] for x in ranked], "start": [members[x] for x in start]}
                if record:
                    out["moves"] = moves
                return out
            last = min(idx, key=lambda x: (pos[x], stack[pos[x]].index(x)))


def run_seed(rules: Rules, setup: dict[str, Any], seed: bytes) -> dict[str, Any]:
    """The real race of [seed]."""
    return run(rules, setup, StreamRng(seed))


# ---------------------------------------------------------------- odds
def estimate(rules: Rules, setup: dict[str, Any], sims: int, rng: Any) -> dict[str, dict[str, int]]:
    """How often each member wins, finishes in the top two, and finishes last over [sims] races of [setup]."""
    members = rules.members
    win = dict.fromkeys(members, 0)
    top2 = dict.fromkeys(members, 0)
    last = dict.fromkeys(members, 0)
    for _ in range(sims):
        r = run(rules, setup, rng, record=False)["ranking"]
        win[r[0]] += 1
        top2[r[0]] += 1
        top2[r[1]] += 1
        last[r[-1]] += 1
    return {"win": win, "top2": top2, "last": last}


def odds_tenths(hits: int, sims: int, payout: float, min_odds: float) -> int:
    """payout / p rounded down to a tenth, with p = hits / sims; at least min_odds, at most MAX_ODDS_TENTHS."""
    if hits <= 0:
        return MAX_ODDS_TENTHS
    per_mille = round(payout * 1000)
    t = per_mille * sims * 10 // (hits * 1000)
    return max(round(min_odds * 10), min(MAX_ODDS_TENTHS, t))


def odds(cfg: dict[str, Any], setup: dict[str, Any], rng: Any, sims: int | None = None) -> dict[str, dict[str, int]]:
    """The odds of every (kind, member), in tenths, from cfg `sims` races of [setup]."""
    rules = Rules.of(cfg)
    n = sims or int(cfg["sims"])
    counts = estimate(rules, setup, n, rng)
    return {kind: {m: odds_tenths(counts[kind][m], n, cfg["payout"], cfg["minOdds"]) for m in rules.members}
            for kind in cfg["kinds"]}
