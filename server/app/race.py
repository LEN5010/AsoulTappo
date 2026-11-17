"""The dumpling race's rules (design §6), with no storage or clock: a race is fully determined by its setup and the
random stream it draws from, and its odds by the coins staked on it.

The track is a lap of `track` squares: square 0 is the start and square `track` the finish, the same corner of the
board. The five dumplings start together on square 0, in lanes drawn at random. Then each rolls a six-sided die for
the order: the higher face moves first, and those on the same face roll again among themselves until they part (see
opening()). The order holds for the whole race: each round all five move once in it. A move rolls a die and carries
every dumpling stacked on the mover along; on square 0 nobody is stacked, so a move from there carries nobody. The
finish must be reached exactly: a roll that would carry the group past it takes it to the finish and back by the
squares left over (bounce()). Landing on an occupied square past the start puts the movers on top. Four kinds of
square act on the group that lands on them, once (wherever it ends up then, nothing acts again): the boost and trip
squares move it on or back; either end of the portal takes it to the other end, on top of whoever is there; the flip
square turns the whole stack there upside down once the group is on it. The race goes on, with no limit on rounds,
until a group lands on the finish; every dumpling is ranked by square, within a square the higher one ahead, and on
square 0 by lane.

Each race deals every member a form (deal_forms()): the faces of the die its moves roll for that race, so the members
are no longer alike. The odds open at each member's chance of each place under its form and the race's squares,
counted over many simulated races (chances()), and move with the coins staked, never past the fair odds: see
odds_tenths(). Races dealt before forms roll the same die for everyone; their odds lean by each member's popularity,
or are the same for all, and stay under the fair odds of alike members.

With `maps` a race is run on one of them instead, drawn at random: a map names its own `track`, optionally the route
its squares take across the board (`path`, read_route(): the start and the finish are then two squares, and nothing
else changes) and its special squares, any number of them, each `{at, kind}`: the four kinds above (boost and trip with `by` squares, a portal with
its other end `to`), `again` (the mover rolls its die once more and the group walks on by it) and `hook` (the group
is pulled onto the nearest occupied square ahead; it stays when there is none).

With `skills` a race deals each member one of them instead of a form (deal_skills()): the faces of its die and what it
does, by id (`chance` in percent and `by` in squares come from the manifest):

- steady: nothing but its die.
- burst: each move, `chance` to walk the die twice.
- chase: moving while last on the track, `by` squares more.
- porter: moving with others on its head, `by` squares more.
- solo: moving with others on its head, `chance` to leave them behind and walk `by` more for each one left.
- dash: need not land on the finish exactly; a move that would carry past it ends on it.
- shield: a trip square, and a portal that would take it back, do nothing to its group.
- climb: when a group lands on its square and it is not on top, it goes to the top.

The real race draws from StreamRng (SHA-256 of the seed), which anyone can recompute from the published seed.
"""
from __future__ import annotations

import hashlib
import math
import random
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
# The special squares a map may hold, and the skills a race may deal.
SQUARE_KINDS = ("boost", "trip", "portal", "flip", "again", "hook")
SKILLS = ("steady", "burst", "chase", "porter", "solo", "dash", "shield", "climb")
# The shortest lap the board is drawn for.
MIN_TRACK = 14
# The largest board a map's route is drawn on: squares across and down.
MAX_BOARD = (16, 10)
# A run of a route: one square at a time to the right, the left, up or down the board.
RUNS = {"R": (1, 0), "L": (-1, 0), "U": (0, -1), "D": (0, 1)}


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
    # How far apart the portal's two ends are, in squares (inclusive).
    portal_gap: tuple[int, int] = (1, 1 << 30)
    # The forms a race deals its members: (id, the faces of its die). None: everyone rolls `dice`.
    forms: tuple[tuple[str, tuple[int, ...]], ...] = ()
    # The maps a race is run on, one drawn for each (read_map()). None: the lap of `track`, five squares dealt.
    maps: tuple[dict[str, Any], ...] = ()
    # The skills a race deals instead of forms (read_skill()).
    skills: tuple[dict[str, Any], ...] = ()

    @classmethod
    def of(cls, cfg: dict[str, Any], members: list[str] | tuple[str, ...]) -> "Rules":
        sq = cfg["squares"]
        gap = sq.get("portalGap") or (1, 1 << 30)
        forms = tuple((str(f["id"]), tuple(int(x) for x in f["dice"])) for f in cfg.get("forms") or ())
        return cls(members=tuple(members), track=int(cfg["track"]), dice=tuple(cfg["dice"]),
                   square_range=(int(sq["range"][0]), int(sq["range"][1])), boost=int(sq["boost"]),
                   trip=int(sq["trip"]), portal_gap=(int(gap[0]), int(gap[1])), forms=forms,
                   maps=tuple(read_map(m) for m in cfg.get("maps") or ()),
                   skills=tuple(read_skill(k) for k in cfg.get("skills") or ()))


def read_route(mid: str, track: int, raw: dict[str, Any]) -> list[list[int]]:
    """A map's route, {from: [col, row], runs: "R8 U2 L8"}, as the board cell of every square from the start (0) to
    the finish (`track`): columns from the left and rows from the top, each run so many squares right, left, up or
    down. Raises ValueError when the runs do not make `track` squares, leave the board (MAX_BOARD), pass a cell twice,
    or bring two squares side by side that are not one after the other: the way must be readable off the board."""
    try:
        col, row = (int(v) for v in raw["from"])
        runs = [(RUNS[r[0]], int(r[1:])) for r in str(raw["runs"]).split()]
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"race map {mid}: a route is {{from: [col, row], runs: 'R8 U2 ...'}}") from None
    cells = [(col, row)]
    for (dc, dr), n in runs:
        if n < 1:
            raise ValueError(f"race map {mid}: a run is 1 square or more")
        for _ in range(n):
            col, row = col + dc, row + dr
            cells.append((col, row))
    if len(cells) != track + 1:
        raise ValueError(f"race map {mid}: the route has {len(cells) - 1} squares, the track {track}")
    if any(not (0 <= c < MAX_BOARD[0] and 0 <= r < MAX_BOARD[1]) for c, r in cells):
        raise ValueError(f"race map {mid}: the route leaves the board of {MAX_BOARD[0]} by {MAX_BOARD[1]}")
    at = {cell: i for i, cell in enumerate(cells)}
    if len(at) != len(cells):
        raise ValueError(f"race map {mid}: the route passes a cell twice")
    for (c, r), i in at.items():
        if any(abs(at.get((c + dc, r + dr), i) - i) > 1 for dc, dr in RUNS.values()):
            raise ValueError(f"race map {mid}: squares that are not one after the other touch at {[c, r]}")
    return [[c, r] for c, r in cells]


def read_map(raw: dict[str, Any]) -> dict[str, Any]:
    """A map of the manifest as a setup carries it: {id, name, track, squares: [{at, kind, by?, to?}], path?}. Without
    a `path` the board is the lap, start and finish in one corner, and the track is even; with one (read_route()) the
    squares lie along it, `path` the cell of each from the start to the finish. Raises ValueError on a map the race
    could not be run on: a short track (an odd one on the lap), an unknown kind, a square on the start or the finish,
    two squares on one, a boost or trip without a whole `by` of 1 or more, a portal whose `to` is not past its
    `at`."""
    mid = str(raw.get("id") or "")
    track = int(raw["track"])
    route = raw.get("path")
    if not mid or track < MIN_TRACK or (track % 2 and not route):
        raise ValueError(f"race map {mid!r}: needs an id and a track of {MIN_TRACK} squares or more, even on the lap")
    squares: list[dict[str, Any]] = []
    taken: set[int] = set()
    for q in raw.get("squares") or ():
        kind, at = q.get("kind"), int(q["at"])
        if kind not in SQUARE_KINDS:
            raise ValueError(f"race map {mid}: unknown square {kind!r}")
        out: dict[str, Any] = {"at": at, "kind": kind}
        ends = [at]
        if kind in ("boost", "trip"):
            out["by"] = int(q["by"])
            if out["by"] < 1:
                raise ValueError(f"race map {mid}: the {kind} square on {at} needs by of 1 or more")
        elif kind == "portal":
            out["to"] = int(q["to"])
            if out["to"] <= at:
                raise ValueError(f"race map {mid}: the portal on {at} must lead further on")
            ends.append(out["to"])
        if any(not 0 < e < track or e in taken for e in ends):
            raise ValueError(f"race map {mid}: square {ends} is off the track or taken")
        taken.update(ends)
        squares.append(out)
    found: dict[str, Any] = {"id": mid, "name": str(raw.get("name") or mid), "track": track, "squares": squares}
    if route:
        found["path"] = read_route(mid, track, route)
    return found


def read_skill(raw: dict[str, Any]) -> dict[str, Any]:
    """A skill of the manifest: {id, dice, chance?, by?}, chance in percent. Raises ValueError on an unknown id, an
    empty die, or a skill without the number it needs."""
    sid = raw.get("id")
    dice = [int(x) for x in raw.get("dice") or ()]
    if sid not in SKILLS or not dice or min(dice) < 1:
        raise ValueError(f"race skill {sid!r}: unknown, or without a die")
    out: dict[str, Any] = {"id": sid, "dice": dice}
    if sid in ("burst", "solo"):
        out["chance"] = int(raw["chance"])
        if not 0 < out["chance"] <= 100:
            raise ValueError(f"race skill {sid}: chance is a percentage above 0")
    if sid in ("chase", "porter", "solo"):
        out["by"] = int(raw.get("by", 1))
        if out["by"] < 1:
            raise ValueError(f"race skill {sid}: by is 1 or more")
    return out


def deal(rules: Rules, rng: Any) -> dict[str, Any]:
    """A race's setup. With maps: {"map": one of them at random}, copied in so that the setup alone replays the
    race. Otherwise five different squares in the range: the portal's two ends [a, b] (a < b, b − a within
    portal_gap), one of the pairs at random, then the boost, trip and flip squares from the rest."""
    if rules.maps:
        return {"map": rng.choice(rules.maps)}
    lo, hi = rules.square_range
    g0, g1 = rules.portal_gap
    pairs = [(a, b) for a in range(lo, hi + 1) for b in range(a + 1, hi + 1) if g0 <= b - a <= g1]
    a, b = rng.choice(pairs)
    boost, trip, flip = rng.sample([q for q in range(lo, hi + 1) if q not in (a, b)], 3)
    return {"boost": boost, "trip": trip, "portal": [a, b], "flip": flip}


def deal_forms(rules: Rules, rng: Any) -> dict[str, Any] | None:
    """Each member's form for one race: {"forms": {member: form id}, "dice": {member: its die's faces}}, the dice
    copied in so that the setup alone replays the race. With at least as many forms as members each member gets a
    different one (rng.sample over the forms, members in manifest order), otherwise each draws one; None without
    forms."""
    if not rules.forms:
        return None
    n = len(rules.members)
    k = len(rules.forms)
    picks = rng.sample(range(k), n) if k >= n else [rng.randrange(k) for _ in range(n)]
    return {"forms": {m: rules.forms[i][0] for m, i in zip(rules.members, picks)},
            "dice": {m: list(rules.forms[i][1]) for m, i in zip(rules.members, picks)}}


def deal_skills(rules: Rules, rng: Any) -> dict[str, Any] | None:
    """Each member's skill for one race: {"skills": {member: {id, chance?, by?}}, "dice": {member: its die's faces}},
    dealt as the forms are: different ones with at least as many skills as members, else one drawn each; None without
    skills."""
    if not rules.skills:
        return None
    n = len(rules.members)
    k = len(rules.skills)
    picks = rng.sample(range(k), n) if k >= n else [rng.randrange(k) for _ in range(n)]
    return {"skills": {m: {key: v for key, v in rules.skills[i].items() if key != "dice"}
                       for m, i in zip(rules.members, picks)},
            "dice": {m: list(rules.skills[i]["dice"]) for m, i in zip(rules.members, picks)}}


def track_of(rules: Rules, setup: dict[str, Any]) -> int:
    """The squares of the lap a setup is run on: its map's, or the manifest's."""
    return int((setup.get("map") or {}).get("track") or rules.track)


def _squares(rules: Rules, setup: dict[str, Any]) -> dict[int, tuple[str, int]]:
    """What acts on each special square of a setup: (kind, its number): the squares a boost pushes on or a trip sets
    back, the other end of a portal, 0 for the rest."""
    acts: dict[int, tuple[str, int]] = {}
    if setup.get("map"):
        for q in setup["map"]["squares"]:
            if q["kind"] == "portal":
                acts[q["at"]] = ("portal", q["to"])
                acts[q["to"]] = ("portal", q["at"])
            else:
                acts[q["at"]] = (q["kind"], int(q.get("by", 0)))
        return acts
    acts[setup["boost"]] = ("boost", rules.boost)
    acts[setup["trip"]] = ("trip", -rules.trip)
    # Setups from before the portal and the flip square have neither.
    if setup.get("portal"):
        a, b = setup["portal"]
        acts[a] = ("portal", b)
        acts[b] = ("portal", a)
    if setup.get("flip") is not None:
        acts[setup["flip"]] = ("flip", 0)
    return acts


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
    """Runs one race. Returns {ranking, start, order, rolls, moves, rest}: ranking first to last; start the lanes on
    the start line, top lane first; order who moves first to last, every round; rolls the order's rounds of dice, each
    [{m, face}] in the order drawn; each move as described in PROTOCOL.md (团子赛跑); rest the dice of those after the
    winning move in the last round, [{m, face}] in the order, which never move.

    Each member rolls its own die, setup["dice"][member], or rules.dice on setups from before forms. Draw order: the
    lanes (one shuffle), the order (opening()), then for each move its die (below(len(its faces))), a burst's chance
    (below(100)), a solo's chance when it has others on its head (below(100)), the second die of an `again` square;
    then rest's dice as the moves' dice."""
    members = rules.members
    below = rng.below
    own = setup.get("dice") or {}
    dice = [tuple(own.get(m) or rules.dice) for m in members]
    track = track_of(rules, setup)
    acts = _squares(rules, setup)
    dealt = setup.get("skills") or {}
    skills = [dealt.get(m) for m in members]
    n = len(members)
    idx = list(range(n))
    climbers = [d for d in idx if skills[d] and skills[d]["id"] == "climb"]

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
        for at, d in enumerate(order):
            faces = dice[d]
            roll = faces[below(len(faces))]
            p = pos[d]
            skill = skills[d]
            sid = skill["id"] if skill else None
            if p:
                s = stack[p]
                k = s.index(d)
                group = s[k:]
                under = s[:k]
            else:
                group = [d]
                under = []
            # What the mover's skill adds to the die, and the skill once it has acted.
            bonus = 0
            used = None
            left: list[int] = []
            if sid == "burst":
                if below(100) < skill["chance"]:
                    bonus, used = roll, sid
            elif sid == "chase":
                if min(idx, key=lambda x: (pos[x], height(x))) == d:
                    bonus, used = skill["by"], sid
            elif sid == "porter":
                if len(group) > 1:
                    bonus, used = skill["by"], sid
            elif sid == "solo":
                if len(group) > 1 and below(100) < skill["chance"]:
                    left, group = group[1:], [d]
                    bonus, used = len(left) * skill["by"], sid
            if p:
                if under or left:
                    stack[p] = under + left
                else:
                    del stack[p]
            steps = roll + bonus

            def reach(square: int) -> int:
                # A dash ends on the finish it would pass; everyone else walks back from it.
                nonlocal used
                if sid == "dash" and square > track:
                    used = sid
                    return track
                return bounce(square, track)

            land = reach(p + steps)
            # Only the square the die gives acts, once: where the group ends up then does nothing more.
            kind, arg = acts.get(land, (None, 0))
            q = land
            thrown = [roll]
            if kind == "boost":
                q = reach(land + arg)
            elif kind == "trip":
                if sid == "shield":
                    kind, used = None, sid
                else:
                    q = bounce(land - arg, track)
            elif kind == "portal":
                if sid == "shield" and arg < land:
                    kind, used = None, sid
                else:
                    q = arg
            elif kind == "again":
                thrown.append(faces[below(len(faces))])
                q = reach(land + thrown[1])
            elif kind == "hook":
                q = min((sq for sq in stack if sq > land), default=land)
            if q:
                stack.setdefault(q, []).extend(group)
            if kind == "flip":
                # The whole stack on the square, the group just landed on top included, turns upside down.
                stack[q].reverse()
            for g in group:
                pos[g] = q
            # A climber the group landed on goes to the top of the square, the lower one first.
            react = [c for c in stack.get(q, ()) if c in climbers and c not in group] if climbers else []
            react = [c for c in react if stack[q][-1] != c or len(react) > 1]
            for c in react:
                stack[q].remove(c)
                stack[q].append(c)
            step: dict[str, Any] = {"m": members[d], "dice": thrown, "steps": steps, "from": p, "to": land}
            if len(group) > 1:
                step["carry"] = [members[g] for g in group[1:]]
            if kind:
                step["square"] = kind
                step["end"] = q
            if used:
                step["skill"] = used
            if left:
                step["left"] = [members[g] for g in left]
            if react:
                step["react"] = [members[c] for c in react]
                step["stack"] = [members[c] for c in stack[q]]
            moves.append(step)
            if q == track:
                ranked = sorted(idx, key=lambda x: (pos[x], height(x)), reverse=True)
                # The rest of the last round still roll, after every draw the race used, only to be shown: the round's
                # dice are thrown together, so its last die gives nothing away.
                rest = [{"m": members[e], "face": dice[e][below(len(dice[e]))]} for e in order[at + 1:]]
                return {"ranking": [members[x] for x in ranked], "start": [members[x] for x in start],
                        "order": [members[x] for x in order], "rolls": rolls, "moves": moves, "rest": rest}


def run_seed(rules: Rules, setup: dict[str, Any], seed: bytes) -> dict[str, Any]:
    """The real race of [seed]."""
    return run(rules, setup, StreamRng(seed))


class SimRng(random.Random):
    """A fast stream for simulated races (chances()); the real race always draws from StreamRng."""

    def below(self, n: int) -> int:
        return self._randbelow(n)


def chances(rules: Rules, setup: dict[str, Any], sims: int, rng: Any) -> dict[str, Any]:
    """How many of [sims] races run on [setup] (its squares and dice) each member wins, ends in the first two and
    ends last: {"sims": sims, "win" | "top2" | "last": {member: count}}. [rng] needs below(); SimRng is quick."""
    members = rules.members
    count = {kind: dict.fromkeys(members, 0) for kind in PLACES}
    for _ in range(sims):
        ranking = run(rules, setup, rng)["ranking"]
        count["win"][ranking[0]] += 1
        count["top2"][ranking[0]] += 1
        count["top2"][ranking[1]] += 1
        count["last"][ranking[-1]] += 1
    return {"sims": sims, **count}


# ---------------------------------------------------------------- odds
def draw_popularity(cfg: dict[str, Any], members: tuple[str, ...] | list[str], rng: Any) -> dict[str, int] | None:
    """Each member's popularity for one race, a whole number drawn evenly from cfg["popularity"] = [lo, hi]
    (inclusive), member by member in manifest order; None when the manifest has no range."""
    span = cfg.get("popularity")
    if not span:
        return None
    lo, hi = int(span[0]), int(span[1])
    return {m: rng.randint(lo, hi) for m in members}


def _weights(kind: str, members: tuple[str, ...] | list[str], popularity: dict[str, int] | None,
             chance: dict[str, Any] | None = None) -> dict[str, int]:
    """Each member's weight in the opening odds for [kind]. With the race's [chance] (chances()): how often it took
    those places, at least 1, so that w × places / Σw is its chance. Otherwise its popularity for win and top2; for last
    the popularity mirrored about the mean (2 × Σw − n × w, scaled by n to stay whole), so the favourite is the least
    backed to come last. 1 each without either (races dealt before them) or when a member has none."""
    if chance and kind in chance:
        return {m: max(1, int(chance[kind].get(m, 0))) for m in members}
    if not popularity or any(m not in popularity for m in members):
        return dict.fromkeys(members, 1)
    if kind != "last":
        return {m: int(popularity[m]) for m in members}
    n = len(members)
    whole = sum(int(popularity[m]) for m in members)
    return {m: 2 * whole - n * int(popularity[m]) for m in members}


def odds_tenths(cfg: dict[str, Any], kind: str, members: tuple[str, ...] | list[str],
                stakes: dict[str, int], popularity: dict[str, int] | None = None,
                chance: dict[str, Any] | None = None) -> dict[str, int]:
    """The odds of each member for [kind], in tenths, given the coins [stakes] on each member for that kind and the
    race's [chance] (chances(); races dealt before forms have none) or, without it, its [popularity].

    With w each member's weight (_weights): share = (stake + depth × w / Σw) / (all stakes + depth), and the odds
    payout / (share × places), rounded down to a tenth, at least minOdds and at most MAX_ODDS_TENTHS. With no stakes
    the share × places is the member's chance p, so the odds open at payout / p. With fairCap the odds are also at
    most fairCap / p (rounded down), whatever the stakes, so a bet never pays more than fairCap of its fair odds; on
    races without [chance] the members are alike and p is places / n, whatever their popularity. Equal weights give
    every member 1 / n of the depth. Exact arithmetic, so the rounding never slips on a float."""
    places = PLACES[kind]
    depth = int(cfg["depth"])
    payout = Fraction(str(cfg["payout"]))
    total = sum(stakes.get(m, 0) for m in members)
    weight = _weights(kind, members, popularity, chance)
    whole = sum(weight.values())
    low = round(Fraction(str(cfg["minOdds"])) * 10)
    cap_ratio = Fraction(str(cfg["fairCap"])) if cfg.get("fairCap") else None
    alike = not (chance and kind in chance)
    out: dict[str, int] = {}
    for m in members:
        # share × places = (stake × Σw + depth × w) × places / (Σw × (total + depth))
        t = math.floor(10 * payout * whole * (total + depth)
                       / ((stakes.get(m, 0) * whole + depth * weight[m]) * places))
        if cap_ratio is not None:
            # The fair odds 1 / p: n / places for alike members, else p = w × places / Σw.
            fair = Fraction(len(members), places) if alike else Fraction(whole, weight[m] * places)
            t = min(t, math.floor(10 * cap_ratio * fair))
        out[m] = max(low, min(MAX_ODDS_TENTHS, t))
    return out


def odds(cfg: dict[str, Any], members: tuple[str, ...] | list[str], stakes: dict[str, dict[str, int]],
         popularity: dict[str, int] | None = None, chance: dict[str, Any] | None = None) -> dict[str, dict[str, int]]:
    """The odds of every (kind, member), in tenths, from the coins staked: stakes[kind][member]."""
    return {kind: odds_tenths(cfg, kind, members, stakes.get(kind, {}), popularity, chance) for kind in cfg["kinds"]}
