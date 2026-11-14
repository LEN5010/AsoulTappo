"""The dumpling race's rules and odds (app/race.py)."""
import hashlib
import json
import random
import statistics
from pathlib import Path

from app import race
from app.manifest import Manifest

M = Manifest.load()
CFG = M.park["race"]
MEMBERS = tuple(c["id"] for c in M.data["characters"])
RULES = race.Rules.of(CFG, MEMBERS)
J, N, B, X, S = "jiaran", "nailin", "beila", "xinyi", "sinuo"
# A shuffle that keeps the order: below(i + 1) answers i for i = 4, 3, 2, 1.
KEEP = [4, 3, 2, 1]
# Order dice in manifest order, all different: 6 5 4 3 2, so the order is the manifest's.
FIRST = [5, 4, 3, 2, 1]


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


def setup(boost=16, trip=17, portal=None, flip=None):
    """A setup; without [portal] or [flip] it has no such square, like the races dealt before them."""
    out = {"boost": boost, "trip": trip}
    if portal:
        out["portal"] = list(portal)
    if flip is not None:
        out["flip"] = flip
    return out


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
        if step.get("square") == "flip":
            stacks[q].reverse()
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
    assert sorted(a["order"]) == sorted(MEMBERS)
    orders = {tuple(race.run_seed(RULES, s, bytes([k]) * 32)["order"]) for k in range(2, 40)}
    assert len(orders) > 10
    for step in a["moves"]:
        assert set(step) <= {"m", "dice", "steps", "from", "to", "carry", "square", "end"}
        assert step.get("square") in (None, "boost", "trip", "portal", "flip")
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


def test_the_order_is_rolled_and_ties_roll_again():
    # Round one J6 N6 B3 X3 S1; J N B X roll again together, 5 2 4 4; B and X once more, 2 5.
    rng = Script(KEEP + [5, 5, 2, 2, 0] + [4, 1, 3, 3] + [1, 4] + [die(1)] * 40)
    out = race.run(RULES, setup(), rng)
    assert out["rolls"] == [
        [{"m": J, "face": 6}, {"m": N, "face": 6}, {"m": B, "face": 3}, {"m": X, "face": 3}, {"m": S, "face": 1}],
        [{"m": J, "face": 5}, {"m": N, "face": 2}, {"m": B, "face": 4}, {"m": X, "face": 4}],
        [{"m": B, "face": 2}, {"m": X, "face": 5}],
    ]
    # A 5 on the reroll does not pass the 6s: each tie is settled among its own.
    assert out["order"] == [J, N, X, B, S]
    # Every round moves in that order.
    assert [m["m"] for m in out["moves"][:10]] == [J, N, X, B, S] * 2


def test_the_order_comes_after_the_lanes_and_before_the_moves():
    # Recomputed from the stream as PROTOCOL.md tells: lanes, the order's dice round by round, then the moves.
    for k in range(200):
        seed = k.to_bytes(32, "big")
        out = race.run_seed(RULES, setup(), seed)
        r = race.StreamRng(seed)
        for i in range(4, 0, -1):
            r.below(i + 1)
        keys = {m: [] for m in MEMBERS}
        rolls = []
        rolling = list(MEMBERS)
        while rolling:
            got = [{"m": m, "face": r.below(6) + 1} for m in rolling]
            for g in got:
                keys[g["m"]].append(g["face"])
            rolls.append(got)
            rolling = [m for m in MEMBERS if [keys[o] for o in MEMBERS].count(keys[m]) > 1]
        assert out["rolls"] == rolls
        assert out["order"] == sorted(MEMBERS, key=lambda m: keys[m], reverse=True)
        assert len({tuple(v) for v in keys.values()}) == len(MEMBERS)
        assert [step["steps"] for step in out["moves"]] == [RULES.dice[r.below(len(RULES.dice))] for _ in out["moves"]]
        assert [step["m"] for step in out["moves"]] == [out["order"][i % 5] for i in range(len(out["moves"]))]
        # Then the rest of the last round, in the order, only to be shown: every round has five dice.
        n = len(out["moves"])
        assert [d["m"] for d in out["rest"]] == out["order"][(n - 1) % 5 + 1:]
        assert (n + len(out["rest"])) % 5 == 0
        assert [d["face"] for d in out["rest"]] == [RULES.dice[r.below(len(RULES.dice))] for _ in out["rest"]]


def test_everyone_starts_side_by_side_and_stacks_form_on_landing():
    # Lanes and order both jiaran, nailin, beila, xinyi, sinuo.
    rng = Script(KEEP + FIRST + [die(3), die(3), die(1), die(2), die(1)] + [die(2), die(1), die(1)])
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
    rng = Script(KEEP + FIRST + [die(3), die(3), die(1), die(1), die(1)] + [die(2), die(1)])
    m = race.run(RULES, setup(boost=5, trip=7), rng)["moves"]
    # jiaran with nailin on top: 3 + 2 lands on the boost square and goes on to 7, past the trip square.
    assert m[5] == {"m": J, "dice": [2], "steps": 2, "from": 3, "to": 5, "square": "boost", "end": 7, "carry": [N]}
    # nailin alone: 7 + 1 = 8.
    assert m[6] == {"m": N, "dice": [1], "steps": 1, "from": 7, "to": 8}
    rng = Script(KEEP + FIRST + [die(3), die(1), die(1), die(1), die(1)] + [die(3)])
    m = race.run(RULES, setup(boost=5, trip=6), rng)["moves"]
    assert m[5] == {"m": J, "dice": [3], "steps": 3, "from": 3, "to": 6, "square": "trip", "end": 5}


def test_a_deal_takes_five_different_squares_with_the_portal_ends_apart():
    lo, hi = RULES.square_range
    g0, g1 = RULES.portal_gap
    assert (g0, g1) == tuple(CFG["squares"]["portalGap"])
    deal = random.Random(1)
    gaps = set()
    for _ in range(2000):
        s = race.deal(RULES, deal)
        a, b = s["portal"]
        squares = [s["boost"], s["trip"], a, b, s["flip"]]
        assert len(set(squares)) == 5 and all(lo <= q <= hi for q in squares)
        assert a < b and g0 <= b - a <= g1
        gaps.add(b - a)
    assert gaps == set(range(g0, g1 + 1))
    # The dealer alone: the same dealer state gives the same setup, and no seed is drawn from.
    assert race.deal(RULES, random.Random(4)) == race.deal(RULES, random.Random(4))


def test_a_portal_takes_the_group_to_the_other_end_on_top():
    # Portal 4 and 8. J 3, N 3 (on J), B 1, X 1, S 1 (on B and X).
    rng = Script(KEEP + FIRST + [die(3), die(3), die(1), die(1), die(1)] + [die(1), die(1), die(3), die(2), die(1)])
    out = race.run(RULES, setup(16, 17, portal=(4, 8)), rng)
    m = out["moves"]
    # J carries N onto 4 and comes out at 8.
    assert m[5] == {"m": J, "dice": [1], "steps": 1, "from": 3, "to": 4, "carry": [N], "square": "portal", "end": 8}
    # N walks on to 9; B carries X and S onto 4 and comes out at 8 on top of J.
    assert m[6] == {"m": N, "dice": [1], "steps": 1, "from": 8, "to": 9}
    assert m[7] == {"m": B, "dice": [3], "steps": 3, "from": 1, "to": 4, "carry": [X, S], "square": "portal", "end": 8}
    # X, over B, leaves with S: J and B stay.
    assert m[8] == {"m": X, "dice": [2], "steps": 2, "from": 8, "to": 10, "carry": [S]}
    assert replay(out) == out["ranking"]
    # Landing on the far end goes back to the near one: J carries N to 6, then N lands on 8 and comes out at 4.
    rng = Script(KEEP + FIRST + [die(3), die(3), die(1), die(1), die(1)] + [die(3), die(2)])
    m = race.run(RULES, setup(16, 17, portal=(4, 8)), rng)["moves"]
    assert m[5] == {"m": J, "dice": [3], "steps": 3, "from": 3, "to": 6, "carry": [N]}
    assert m[6] == {"m": N, "dice": [2], "steps": 2, "from": 6, "to": 8, "square": "portal", "end": 4}


def test_the_flip_square_turns_its_stack_upside_down():
    # Flip on 3. J 3 lands on the empty flip square: it flips its own stack of one. N 3 lands on J: [J, N] turns to
    # [N, J]. B 3 on top of that: [N, J, B] turns to [B, J, N]; nobody else moved, the residents turned with it.
    rng = Script(KEEP + FIRST + [die(3), die(3), die(3), die(1), die(1)] + [die(1)])
    out = race.run(RULES, setup(16, 17, flip=3), rng)
    m = out["moves"]
    assert m[0] == {"m": J, "dice": [3], "steps": 3, "from": 0, "to": 3, "square": "flip", "end": 3}
    assert m[1] == {"m": N, "dice": [3], "steps": 3, "from": 0, "to": 3, "square": "flip", "end": 3}
    assert m[2] == {"m": B, "dice": [3], "steps": 3, "from": 0, "to": 3, "square": "flip", "end": 3}
    # Next round J, now in the middle, carries N (above it) and leaves B behind.
    assert m[5] == {"m": J, "dice": [1], "steps": 1, "from": 3, "to": 4, "carry": [N]}
    assert replay(out) == out["ranking"]


def test_a_special_square_acts_once():
    # Boost 4 pushes J onto the portal at 6: it stays there.
    rng = Script(KEEP + FIRST + [die(3), die(1), die(1), die(1), die(1)] + [die(1)])
    m = race.run(RULES, setup(4, 5, portal=(6, 11)), rng)["moves"]
    assert m[5] == {"m": J, "dice": [1], "steps": 1, "from": 3, "to": 4, "square": "boost", "end": 6}
    # Flip 4, trip 5. J carries B, X, S onto the flip square: [J B X S] turns to [S X B J]. N falls back from the trip
    # square onto the flip square, on top, and nothing turns: B then carries J and N.
    rng = Script(KEEP + FIRST + [die(1), die(3), die(1), die(1), die(1)] + [die(3), die(2), die(2)])
    m = race.run(RULES, setup(16, 5, flip=4), rng)["moves"]
    assert m[5] == {"m": J, "dice": [3], "steps": 3, "from": 1, "to": 4, "carry": [B, X, S], "square": "flip", "end": 4}
    assert m[6] == {"m": N, "dice": [2], "steps": 2, "from": 3, "to": 5, "square": "trip", "end": 4}
    assert m[7] == {"m": B, "dice": [2], "steps": 2, "from": 4, "to": 6, "carry": [J, N]}


def test_an_old_setup_without_portal_or_flip_still_runs():
    seed = b"\x07" * 32
    old = race.run_seed(RULES, setup(9, 12), seed)
    assert all(step.get("square") in (None, "boost", "trip") for step in old["moves"])
    assert replay(old) == old["ranking"]


def test_the_finish_must_be_reached_exactly():
    # A short track: 3 from square 0 lands on the finish; 3 from square 2 goes to 4 and walks back to 2.
    rules = race.Rules(members=MEMBERS, track=4, dice=(1, 2, 3), square_range=(10, 11), boost=2, trip=-1)
    assert race.bounce(5, 4) == 3 and race.bounce(6, 4) == 2 and race.bounce(4, 4) == 4 and race.bounce(-1, 4) == 0
    # Order J N B X S; J 2, N 2 (on top of J), B 1, X 1, S 1; then J rolls 3 carrying N: 2 + 3 = 5, back to 3.
    rng = Script(KEEP + FIRST + [1, 1, 0, 0, 0] + [2] + [0, 0, 0, 0] + [0, 0, 0, 0, 0])
    m = race.run(rules, setup(10, 11), rng)["moves"]
    assert m[5] == {"m": J, "dice": [3], "steps": 3, "from": 2, "to": 3, "carry": [N]}
    # Bounced onto the trip square: it acts as on any landing. Everyone rolls 1 onto square 1, J carries the stack to
    # 4, then N (with those above) rolls 3: 7 walks back to 5, the trip square, and falls to 4.
    rules = race.Rules(members=MEMBERS, track=6, dice=(1, 2, 3), square_range=(5, 5), boost=2, trip=-1)
    rng = Script(KEEP + FIRST + [0, 0, 0, 0, 0] + [2, 2])
    m = race.run(rules, {"boost": 2, "trip": 5}, rng)["moves"]
    assert m[5] == {"m": J, "dice": [3], "steps": 3, "from": 1, "to": 4, "carry": [N, B, X, S]}
    assert m[6] == {"m": N, "dice": [3], "steps": 3, "from": 4, "to": 5, "carry": [B, X, S], "square": "trip",
                    "end": 4}


def test_dumplings_still_on_the_start_rank_by_lane():
    # A one-move race: the first to move finishes, the rest never left square 0.
    rules = race.Rules(members=MEMBERS, track=3, dice=(3,), square_range=(10, 11), boost=2, trip=-1)
    # Lanes sinuo, nailin, beila, xinyi, jiaran (swap 4 with 0); beila rolls the 6 and moves first.
    out = race.run(rules, setup(10, 11), Script([0, 3, 2, 1, 0, 1, 5, 2, 3, 0]))
    assert out["start"] == [S, N, B, X, J]
    assert out["moves"] == [{"m": B, "dice": [3], "steps": 3, "from": 0, "to": 3}]
    assert out["ranking"] == [B, S, N, X, J]


def test_ranking_follows_squares_then_height():
    deal = random.Random(2)
    winner_rode = 0
    kinds = set()
    for k in range(300):
        out = race.run_seed(RULES, race.deal(RULES, deal), k.to_bytes(32, "big"))
        kinds |= {step.get("square") for step in out["moves"]}
        assert replay(out) == out["ranking"]
        assert len(out["moves"]) > 5
        assert all("carry" not in step for step in out["moves"] if step["from"] == 0)
        last = out["moves"][-1]
        assert last.get("end", last["to"]) == RULES.track
        for step in out["moves"]:
            assert 0 <= step.get("end", step["to"]) <= RULES.track
        assert out["ranking"][0] in [last["m"], *last.get("carry", [])]
        winner_rode += out["ranking"][0] != last["m"]
    # The winner is the top of the group that gets there, often not the one that moved.
    assert winner_rode > 30
    assert kinds == {None, "boost", "trip", "portal", "flip"}


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


def test_popularity_is_drawn_from_the_range_for_every_member():
    lo, hi = CFG["popularity"]
    rng = random.Random(1)
    seen = set()
    for _ in range(500):
        pop = race.draw_popularity(CFG, MEMBERS, rng)
        assert list(pop) == list(MEMBERS) and all(lo <= w <= hi for w in pop.values())
        seen.update(pop.values())
    assert seen == set(range(lo, hi + 1))
    assert race.draw_popularity({k: v for k, v in CFG.items() if k != "popularity"}, MEMBERS, rng) is None


def test_odds_lean_on_popularity():
    pop = {J: 108, N: 92, B: 100, X: 100, S: 100}
    o = race.odds(CFG, MEMBERS, {}, pop)
    # win: 0.85 × 500 / 108 = 3.94, / 92 = 4.62, / 100 = 4.25; top two half that.
    assert o["win"] == {J: 39, N: 46, B: 42, X: 42, S: 42}
    assert o["top2"] == {J: 19, N: 23, B: 21, X: 21, S: 21}
    # last mirrors the weights about the mean (1000 − 5w: 460, 540, 500), so the favourite pays more to come last.
    assert o["last"] == {J: 46, N: 39, B: 42, X: 42, S: 42}
    # Stakes move them as before: 50 on jiaran, 0.85 × 500 × 150 / (50 × 500 + 100 × 108) = 1.78.
    assert race.odds_tenths(CFG, "win", MEMBERS, {J: 50}, pop) == {J: 17, N: 69, B: 63, X: 63, S: 63}
    # Even popularity, none, or a member without one: the flat odds.
    flat = race.odds(CFG, MEMBERS, {})
    assert race.odds(CFG, MEMBERS, {}, dict.fromkeys(MEMBERS, 97)) == flat
    assert race.odds(CFG, MEMBERS, {}, None) == flat
    assert race.odds(CFG, MEMBERS, {}, {J: 108}) == flat


def test_the_best_opening_odds_stay_below_even_money():
    # Every kind at the far ends of the range, one member against the other four: p × odds < 1 for every selection.
    lo, hi = CFG["popularity"]
    for one, rest in ((lo, hi), (hi, lo)):
        for m in MEMBERS:
            pop = {x: one if x == m else rest for x in MEMBERS}
            for kind, places in race.PLACES.items():
                best = max(race.odds_tenths(CFG, kind, MEMBERS, {}, pop).values())
                assert best / 10 * places / len(MEMBERS) < 1, (kind, pop)


# ---------------------------------------------------------------- the client's replay
# Races the client replays in race.test.ts (boardOf, stacksAt, rankOf) to the server's ranking. Dealt by
# race.deal(RULES, random.Random(k)) with seed k as 32 bytes; between them they cover portals both ways and onto an
# occupied end, flips with others under the group and of a group alone, carrying, walking back from the finish and a
# winner riding on top. The last is a race dealt before the portal and flip squares. Written by running this file
# from server/ (PYTHONPATH=. .venv/bin/python tests/test_race.py).
FIXTURE = Path(__file__).resolve().parents[2] / "client/src/panel/park/race.fixture.json"
FIXTURE_DEALS = [1, 2, 53]
FIXTURE_OLD = (7, {"boost": 9, "trip": 12})


def fixture_races():
    out = []
    for k in FIXTURE_DEALS:
        out.append((k, race.deal(RULES, random.Random(k))))
    out.append(FIXTURE_OLD)
    races = []
    for k, s in out:
        r = race.run_seed(RULES, s, k.to_bytes(32, "big"))
        races.append({"seed": k.to_bytes(32, "big").hex(), "setup": s, "start": r["start"], "order": r["order"],
                      "moves": r["moves"], "rest": r["rest"], "ranking": r["ranking"]})
    return races


def test_the_client_fixture_is_what_the_rules_give():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == {"track": RULES.track, "boost": RULES.boost,
                                                                "trip": RULES.trip, "races": fixture_races()}
    for r in fixture_races():
        assert replay(r) == r["ranking"]


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps({"track": RULES.track, "boost": RULES.boost, "trip": RULES.trip,
                                   "races": fixture_races()}, ensure_ascii=False) + "\n", encoding="utf-8")
