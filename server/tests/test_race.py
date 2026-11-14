"""The dumpling race's rules and odds (app/race.py)."""
import hashlib
import random
import statistics

from app import race
from app.manifest import Manifest

M = Manifest.load()
CFG = M.park["race"]
MEMBERS = tuple(c["id"] for c in M.data["characters"])
RULES = race.Rules.of(CFG, MEMBERS)
J, N, B, X, S = "jiaran", "nailin", "beila", "xinyi", "sinuo"
# A shuffle that keeps the order: below(i + 1) answers i for i = 4, 3, 2, 1.
KEEP = [4, 3, 2, 1]


class Script:
    """Hands out the scripted below() values, then falls back to a seeded generator."""

    def __init__(self, belows):
        self.belows = list(belows)
        self.rest = random.Random(0)

    def below(self, n):
        if self.belows:
            v = self.belows.pop(0)
            assert 0 <= v < n
            return v
        return self.rest.randrange(n)


def die(n):
    """The below() answer that rolls [n]."""
    return RULES.dice.index(n)


def setup(boost=16, trip=17):
    return {"boost": boost, "trip": trip}


def replay(out):
    """Rebuilds the final places from the lanes and the move list as a client would, and ranks from them."""
    lane = {m: i for i, m in enumerate(out["start"])}
    pos = dict.fromkeys(out["start"], 0)
    stacks = {}
    for step in out["moves"]:
        if step["from"]:
            s = stacks[step["from"]]
            k = s.index(step["m"])
            group = s[k:]
            stacks[step["from"]] = s[:k]
        else:
            group = [step["m"]]
        assert group[1:] == step.get("carry", [])
        q = step.get("end", step["to"])
        if q:
            stacks.setdefault(q, []).extend(group)
        for m in group:
            pos[m] = q
    return sorted(pos, key=lambda m: (pos[m], stacks[pos[m]].index(m) if pos[m] else -lane[m]), reverse=True)


def test_stream_rng_is_sha256_of_seed_and_counter():
    seed = bytes(range(32))
    r = race.StreamRng(seed)
    block = hashlib.sha256(seed + (0).to_bytes(8, "big")).digest()
    words = [int.from_bytes(block[i:i + 4], "big") for i in range(0, 32, 4)]
    assert [r.below(1 << 31) for _ in range(8)] == [w % (1 << 31) for w in words]
    assert race.seed_hash(seed) == hashlib.sha256(seed).hexdigest()


def test_members_come_in_manifest_order():
    assert RULES.members == (J, N, B, X, S)


def test_a_seed_decides_the_whole_race():
    s = setup(9, 12)
    a = race.run_seed(RULES, s, b"\x01" * 32)
    assert a == race.run_seed(RULES, s, b"\x01" * 32)
    others = {tuple(race.run_seed(RULES, s, bytes([k]) * 32)["ranking"]) for k in range(2, 40)}
    assert len(others) > 10
    lanes = {tuple(race.run_seed(RULES, s, bytes([k]) * 32)["start"]) for k in range(2, 40)}
    assert len(lanes) > 10
    assert sorted(a["ranking"]) == sorted(MEMBERS) and sorted(a["start"]) == sorted(MEMBERS)
    for step in a["moves"]:
        assert set(step) <= {"m", "dice", "steps", "from", "to", "carry", "square", "end"}
        assert step["dice"] == [step["steps"]] and step["steps"] in RULES.dice


def test_the_lanes_come_first_from_the_seed():
    # The lanes are the first shuffle of the stream: below(5), below(4), below(3), below(2).
    seed = b"\x05" * 32
    r = race.StreamRng(seed)
    lanes = list(range(5))
    for i in range(4, 0, -1):
        j = r.below(i + 1)
        lanes[i], lanes[j] = lanes[j], lanes[i]
    assert race.run_seed(RULES, setup(), seed)["start"] == [MEMBERS[i] for i in lanes]


def test_everyone_starts_side_by_side_and_stacks_form_on_landing():
    # Lanes and round order both jiaran, nailin, beila, xinyi, sinuo.
    rng = Script(KEEP + KEEP + [die(3), die(3), die(1), die(2), die(1)] + KEEP + [die(2), die(1), die(1)])
    out = race.run(RULES, setup(), rng)
    assert out["start"] == [J, N, B, X, S]
    m = out["moves"]
    # Moves from the start carry nobody, even with others still on square 0.
    assert m[0] == {"m": J, "dice": [3], "steps": 3, "from": 0, "to": 3}
    # nailin lands on jiaran and goes on top, carrying nobody on the way.
    assert m[1] == {"m": N, "dice": [3], "steps": 3, "from": 0, "to": 3}
    assert m[2] == {"m": B, "dice": [1], "steps": 1, "from": 0, "to": 1}
    assert m[3] == {"m": X, "dice": [2], "steps": 2, "from": 0, "to": 2}
    assert m[4] == {"m": S, "dice": [1], "steps": 1, "from": 0, "to": 1}
    # Now jiaran carries nailin; nailin on top moves alone; beila carries sinuo, who landed on it.
    assert m[5] == {"m": J, "dice": [2], "steps": 2, "from": 3, "to": 5, "carry": [N]}
    assert m[6] == {"m": N, "dice": [1], "steps": 1, "from": 5, "to": 6}
    assert m[7] == {"m": B, "dice": [1], "steps": 1, "from": 1, "to": 2, "carry": [S]}
    # beila and sinuo landed on xinyi: xinyi at the bottom carries both.
    assert m[8]["m"] == X and m[8]["carry"] == [B, S]


def test_boost_and_trip_squares_move_the_whole_group():
    rng = Script(KEEP + KEEP + [die(3), die(3), die(1), die(1), die(1)] + KEEP + [die(2), die(1)])
    m = race.run(RULES, setup(boost=5, trip=7), rng)["moves"]
    # jiaran with nailin on top: 3 + 2 lands on the boost square and goes on to 7, past the trip square.
    assert m[5] == {"m": J, "dice": [2], "steps": 2, "from": 3, "to": 5, "square": "boost", "end": 7, "carry": [N]}
    # nailin alone: 7 + 1 = 8.
    assert m[6] == {"m": N, "dice": [1], "steps": 1, "from": 7, "to": 8}
    rng = Script(KEEP + KEEP + [die(3), die(1), die(1), die(1), die(1)] + KEEP + [die(3)])
    m = race.run(RULES, setup(boost=5, trip=6), rng)["moves"]
    assert m[5] == {"m": J, "dice": [3], "steps": 3, "from": 3, "to": 6, "square": "trip", "end": 5}


def test_dumplings_still_on_the_start_rank_by_lane():
    # A one-move race: the first to move finishes, the rest never left square 0.
    rules = race.Rules(members=MEMBERS, track=3, dice=(3,), square_range=(10, 11), boost=2, trip=-1)
    # Lanes sinuo, nailin, beila, xinyi, jiaran (swap 4 with 0); beila moves first.
    out = race.run(rules, setup(10, 11), Script([0, 3, 2, 1, 4, 3, 0, 1, 0]))
    assert out["start"] == [S, N, B, X, J]
    assert out["moves"] == [{"m": B, "dice": [3], "steps": 3, "from": 0, "to": 3}]
    assert out["ranking"] == [B, S, N, X, J]


def test_ranking_follows_squares_then_height():
    s = setup(6, 11)
    winner_rode = 0
    for k in range(300):
        out = race.run_seed(RULES, s, k.to_bytes(32, "big"))
        assert replay(out) == out["ranking"]
        assert len(out["moves"]) > 5
        assert all("carry" not in step for step in out["moves"] if step["from"] == 0)
        last = out["moves"][-1]
        assert last.get("end", last["to"]) >= RULES.track
        assert out["ranking"][0] in [last["m"], *last.get("carry", [])]
        winner_rode += out["ranking"][0] != last["m"]
    # The winner is the top of the group that gets there, often not the one that moved.
    assert winner_rode > 30


def test_every_member_has_the_same_chances():
    n = 6000
    win = dict.fromkeys(MEMBERS, 0)
    top2 = dict.fromkeys(MEMBERS, 0)
    last = dict.fromkeys(MEMBERS, 0)
    rounds = []
    deal = random.Random(5)
    for k in range(n):
        out = race.run_seed(RULES, race.deal(RULES, deal), k.to_bytes(32, "big"))
        r = out["ranking"]
        win[r[0]] += 1
        top2[r[0]] += 1
        top2[r[1]] += 1
        last[r[-1]] += 1
        rounds.append(-(-len(out["moves"]) // 5))
    for m in MEMBERS:
        assert abs(win[m] / n - 0.2) < 0.025, m
        assert abs(top2[m] / n - 0.4) < 0.03, m
        assert abs(last[m] / n - 0.2) < 0.025, m
    assert 4 < statistics.mean(rounds) < 8


def test_odds_with_nothing_staked():
    o = race.odds(CFG, MEMBERS, {})
    assert o == {"win": dict.fromkeys(MEMBERS, 42), "top2": dict.fromkeys(MEMBERS, 21),
                 "last": dict.fromkeys(MEMBERS, 42)}


def test_odds_follow_the_stakes():
    # win, 50 on jiaran: its share (50 + 20) / 150, 0.85 / 0.4667 = 1.82; the others' 20 / 150, 6.375.
    o = race.odds_tenths(CFG, "win", MEMBERS, {J: 50})
    assert o == {J: 18, N: 63, B: 63, X: 63, S: 63}
    # top2, 30 on nailin and 10 on beila: Σp = 2; nailin (30 + 20) / 140 × 2 → 0.85 / 0.714 = 1.19.
    o = race.odds_tenths(CFG, "top2", MEMBERS, {N: 30, B: 10})
    assert o == {J: 29, N: 11, B: 19, X: 29, S: 29}
    # Exactly a tenth: 100 on nailin gives the others 0.85 × 5 × 200 / 100 = 8.5, not 8.4 from float noise.
    assert race.odds_tenths(CFG, "win", MEMBERS, {N: 100})[J] == 85
    # Clamped to minOdds and the most.
    o = race.odds_tenths(CFG, "last", MEMBERS, {J: 10000})
    assert o[J] == round(CFG["minOdds"] * 10) and o[N] == race.MAX_ODDS_TENTHS
    # Stakes on other kinds do not move this one.
    assert race.odds(CFG, MEMBERS, {"win": {J: 50}})["last"] == dict.fromkeys(MEMBERS, 42)


def test_odds_return_payout_on_a_balanced_book():
    # Stakes spread in proportion to the chances: every selection pays payout / p.
    for kind, places in race.PLACES.items():
        o = race.odds_tenths(CFG, kind, MEMBERS, dict.fromkeys(MEMBERS, 40))
        p = places / len(MEMBERS)
        assert all(abs(t / 10 - CFG["payout"] / p) < 0.1 for t in o.values()), kind
