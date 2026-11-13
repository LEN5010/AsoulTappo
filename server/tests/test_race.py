"""The dumpling race's rules (app/race.py)."""
import hashlib
import random
import statistics

from app import race
from app.manifest import Manifest

CFG = Manifest.load().park["race"]
RULES = race.Rules.of(CFG)
J, N, B, X, S = "jiaran", "nailin", "beila", "xinyi", "sinuo"


class Script:
    """Hands out the scripted below() and random() values, then falls back to a seeded generator."""

    def __init__(self, belows, randoms):
        self.belows = list(belows)
        self.randoms = list(randoms)
        self.rest = race.PyRng(random.Random(0))

    def below(self, n):
        if self.belows:
            v = self.belows.pop(0)
            assert 0 <= v < n
            return v
        return self.rest.below(n)

    def random(self):
        return self.randoms.pop(0) if self.randoms else self.rest.random()


def setup(moods=None, boost=16, trip=17):
    return {"moods": moods or dict.fromkeys(RULES.members, "normal"), "boost": boost, "trip": trip}


def replay(out, track=RULES.track):
    """Rebuilds the final stacks from the move list as a client would, and ranks from them."""
    stacks = {0: list(out["start"])}
    for step in out["moves"]:
        s = stacks[step["from"]]
        k = s.index(step["m"])
        group = s[k:]
        assert group[1:] == step.get("carry", [])
        stacks[step["from"]] = s[:k]
        stacks.setdefault(step.get("end", step["to"]), []).extend(group)
    order = sorted(((sq, h, m) for sq, s in stacks.items() for h, m in enumerate(s)), reverse=True)
    return [m for _, _, m in order]


def test_stream_rng_is_sha256_of_seed_and_counter():
    seed = bytes(range(32))
    r = race.StreamRng(seed)
    block = hashlib.sha256(seed + (0).to_bytes(8, "big")).digest()
    first = int.from_bytes(block[:4], "big")
    assert r.below(1 << 31) == first % (1 << 31)
    assert race.seed_hash(seed) == hashlib.sha256(seed).hexdigest()
    r = race.StreamRng(seed)
    words = [int.from_bytes(block[i:i + 4], "big") for i in (0, 4)]
    assert r.random() == ((words[0] >> 5) * 67108864 + (words[1] >> 6)) / 2 ** 53


def test_a_seed_decides_the_whole_race():
    s = setup({J: "hot", N: "excited", B: "normal", X: "sleepy", S: "slacking"}, 9, 12)
    a = race.run_seed(RULES, s, b"\x01" * 32)
    assert a == race.run_seed(RULES, s, b"\x01" * 32)
    others = {tuple(race.run_seed(RULES, s, bytes([k]) * 32)["ranking"]) for k in range(2, 40)}
    assert len(others) > 10
    assert sorted(a["ranking"]) == sorted(RULES.members) and sorted(a["start"]) == sorted(RULES.members)


def test_steady_snack_dash_reroll_and_carrying():
    # Start stack and round order both jiaran, nailin, beila, xinyi, sinuo (bottom to top).
    rng = Script([4, 3, 2, 1, 4, 3, 2, 1, 0, 2, 0, 1, 0, 4, 3, 2, 1, 1], [0.1, 0.1, 0.1])
    m = race.run(RULES, setup(), rng)["moves"]
    # jiaran at the bottom rolls 1, carries everyone and gets a snack (chance 0.1 < 0.5).
    assert m[0] == {"m": J, "dice": [1], "steps": 1, "from": 0, "to": 1, "snack": 1, "carry": [N, B, X, S]}
    # nailin always goes 2 and takes the three above it along; jiaran stays.
    assert m[1] == {"m": N, "dice": [], "steps": 2, "from": 1, "to": 3, "carry": [B, X, S]}
    # beila rolls 3 and dashes one more.
    assert m[2] == {"m": B, "dice": [3], "steps": 4, "from": 3, "to": 7, "add": [["dash", 1]], "carry": [X, S]}
    # xinyi rolls 1 and rolls again.
    assert m[3] == {"m": X, "dice": [1, 2], "steps": 2, "from": 7, "to": 9, "carry": [S]}
    assert m[4] == {"m": S, "dice": [1], "steps": 1, "from": 9, "to": 10}
    # Next round jiaran eats the snack: one more square, and no chance drawn.
    assert m[5] == {"m": J, "dice": [2], "steps": 3, "from": 1, "to": 4, "add": [["snack", 1]]}


def test_moods_catchup_and_landing_on_top():
    moods = {S: "hot", J: "sleepy", N: "slacking", B: "excited", X: "normal"}
    # Start stack sinuo, nailin, beila, xinyi, jiaran (bottom to top); rounds go jiaran, nailin, beila, xinyi, sinuo.
    rng = Script([0, 3, 2, 1, 4, 3, 2, 1, 0, 1, 1, 1, 4, 3, 2, 1, 2, 2], [0.9, 0.1])
    m = race.run(RULES, setup(moods), rng)["moves"]
    # Sleepy: one square less, but at least one.
    assert m[0] == {"m": J, "dice": [1], "steps": 1, "from": 0, "to": 1, "add": [["mood", 0]]}
    # Slacking nailin goes 1 and lands on jiaran.
    assert m[1] == {"m": N, "dice": [], "steps": 1, "from": 0, "to": 1, "add": [["mood", -1]], "carry": [B, X]}
    assert m[2] == {"m": B, "dice": [2], "steps": 3, "from": 1, "to": 4, "add": [["mood", 1]], "carry": [X]}
    assert m[3] == {"m": X, "dice": [2], "steps": 2, "from": 4, "to": 6}
    # sinuo is last at its turn: one more, and hot: one more again.
    assert m[4] == {"m": S, "dice": [2], "steps": 4, "from": 0, "to": 4, "add": [["catchup", 1], ["mood", 1]]}
    # nailin sits on jiaran, so jiaran carries it.
    assert m[5] == {"m": J, "dice": [3], "steps": 2, "from": 1, "to": 3, "add": [["mood", -1]], "carry": [N]}
    assert m[6] == {"m": N, "dice": [], "steps": 1, "from": 3, "to": 4, "add": [["mood", -1]]}
    # beila is under sinuo and nailin now (both landed on top of it) and takes them along.
    assert m[7] == {"m": B, "dice": [3], "steps": 5, "from": 4, "to": 9, "add": [["dash", 1], ["mood", 1]],
                    "carry": [S, N]}


def test_moods_wear_off():
    moods = {J: "hot", N: "excited", B: "normal", X: "sleepy", S: "slacking"}
    out = race.run_seed(RULES, setup(moods), b"\x07" * 32)
    for member, mood in moods.items():
        mine = [s for s in out["moves"] if s["m"] == member]
        n = RULES.moods[mood]["moves"] if RULES.moods[mood]["delta"] else 0
        assert all(any(a[0] == "mood" for a in s.get("add", [])) for s in mine[:n])
        assert not any(any(a[0] == "mood" for a in s.get("add", [])) for s in mine[n:])


def test_boost_and_trip_squares_move_the_whole_group():
    rng = Script([4, 3, 2, 1, 4, 3, 2, 1, 2, 0], [0.9])
    m = race.run(RULES, setup(boost=5, trip=8), rng)["moves"]
    assert m[0] == {"m": J, "dice": [3], "steps": 3, "from": 0, "to": 3, "carry": [N, B, X, S]}
    assert m[1] == {"m": N, "dice": [], "steps": 2, "from": 3, "to": 5, "square": "boost", "end": 7,
                    "carry": [B, X, S]}
    assert m[2] == {"m": B, "dice": [1], "steps": 1, "from": 7, "to": 8, "square": "trip", "end": 7,
                    "carry": [X, S]}


def test_ranking_follows_squares_then_height():
    s = setup({J: "hot", N: "excited", B: "normal", X: "sleepy", S: "slacking"}, 6, 11)
    winner_rode = 0
    for k in range(300):
        out = race.run_seed(RULES, s, k.to_bytes(32, "big"))
        assert replay(out) == out["ranking"]
        last = out["moves"][-1]
        assert last.get("end", last["to"]) >= RULES.track
        assert out["ranking"][0] in [last["m"], *last.get("carry", [])]
        winner_rode += out["ranking"][0] != last["m"]
    # The winner is the top of the group that gets there, often not the one that moved.
    assert winner_rode > 30


def test_win_rates_match_the_design():
    rng = random.Random(5)
    n = 30000
    skills = dict.fromkeys(RULES.members, 0)
    moods = {m: 0 for m in RULES.moods}
    rounds = []
    for _ in range(n):
        s = race.deal(RULES, rng)
        out = race.run(RULES, s, race.PyRng(rng))
        moods[s["moods"][out["ranking"][0]]] += 1
        rounds.append(-(-len(out["moves"]) // 5))
        s["moods"] = dict.fromkeys(RULES.members, "normal")
        skills[race.run(RULES, s, race.PyRng(rng), record=False)["ranking"][0]] += 1
    # Design §6.2 (no moods) and §6.3 (moods dealt).
    for member, rate in {J: .206, N: .167, B: .202, X: .211, S: .214}.items():
        assert abs(skills[member] / n - rate) < 0.015, member
    for mood, rate in {"hot": .358, "excited": .238, "normal": .187, "sleepy": .128, "slacking": .089}.items():
        assert abs(moods[mood] / n - rate) < 0.015, mood
    assert 5.0 < statistics.mean(rounds) < 5.8


def test_odds_round_down_to_a_tenth_within_bounds():
    assert race.odds_tenths(4000, 20000, 0.85, 1.1) == 42
    assert race.odds_tenths(19000, 20000, 0.85, 1.1) == 11
    assert race.odds_tenths(0, 20000, 0.85, 1.1) == race.MAX_ODDS_TENTHS
    assert race.odds_tenths(1, 20000, 0.85, 1.1) == race.MAX_ODDS_TENTHS


def test_odds_return_83_to_85_percent():
    # 30 setups, odds and the true chances from separate fixed-seed sims (3000 each; the server uses `sims`).
    rng = random.Random(1)
    ret = {k: [] for k in CFG["kinds"]}
    for i in range(30):
        s = race.deal(RULES, rng)
        odds = race.odds(CFG, s, race.PyRng(random.Random(1000 + i)), sims=3000)
        true = race.estimate(RULES, s, 3000, race.PyRng(random.Random(900000 + i)))
        for kind in ret:
            ret[kind] += [odds[kind][m] / 10 * true[kind][m] / 3000 for m in RULES.members]
    pooled = statistics.mean(sum(ret.values(), []))
    assert 0.83 <= pooled <= 0.85
    # Design §6.4: win 84%, top two 83%, last 84%.
    for kind, design in {"win": .84, "top2": .83, "last": .84}.items():
        assert abs(statistics.mean(ret[kind]) - design) < 0.01, kind
