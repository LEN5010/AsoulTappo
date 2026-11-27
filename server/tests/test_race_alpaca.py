"""The dumpling race with the order drawn every round and the alpaca (app/race.py), and how app/park_race.py paces
such a race and keeps it from clients before 1.3.0."""
import json
import random

import pytest

from app import park_race, race
from app.game import Game
from app.manifest import Manifest
from app.park import Park
from app.park_race import Races
from app.store import Store
import gen_race_alpaca_fixture
from fixtures import Clock
from test_race import FIRST, KEEP, Script
from test_race_park import T0, TOKEN, seeds

M = Manifest.load()
CFG = M.park["race"]
MEMBERS = tuple(c["id"] for c in M.data["characters"])
J, N, B, X, S = MEMBERS
A = race.ALPACA
DICE = (1, 2, 3, 4, 5, 6)
OPEN = KEEP + FIRST


def die(n):
    """The below() answer that rolls [n], on the members' dice and on the alpaca's."""
    return DICE.index(n)


def rules(track=20, squares=(), shuffle=False, alpaca=True, skills=()):
    cfg = {**CFG, "dice": list(DICE), "maps": [{"id": "t", "track": track, "squares": list(squares)}],
           "skills": list(skills), "shuffle": shuffle}
    cfg.pop("alpaca", None)
    if alpaca:
        cfg["alpaca"] = {"dice": list(DICE)}
    return race.Rules.of(cfg, MEMBERS)


def setup(r):
    su = {"map": r.maps[0]}
    su.update(race.deal_rules(r, su))
    return su


def replay(out, track):
    """The final ranking rebuilt from the lanes, the moves and the alpaca's drives alone, as a client does, checking
    each drive against the board: it leaves from the alpaca's square (or the finish, `back`), carries the squares it
    passes bottom to top, and goes home only with nobody left ahead of it."""
    lane = {m: i for i, m in enumerate(out["start"])}
    pos = dict.fromkeys(out["start"], 0)
    stacks: dict[int, list[str]] = {}
    drives = list(out.get("drives", []))
    car = None
    for i, step in enumerate(out["moves"]):
        while drives and drives[0]["at"] == i:
            d = drives.pop(0)
            assert car is not None
            ahead = [m for m in pos if 0 < pos[m] < car]
            if "back" in d:
                assert d["back"] == car != track and not ahead
                car = track
            else:
                assert ahead
            assert d["from"] == car and d["to"] == max(1, car - d["face"])
            took = [m for sq in range(d["to"], d["from"] + 1) for m in stacks.pop(sq, [])]
            assert took == d.get("take", [])
            if took:
                stacks[d["to"]] = took
                for m in took:
                    pos[m] = d["to"]
            car = d["to"]
            if d.get("home"):
                assert not [m for m in pos if 0 < pos[m] < car]
                car = track
            else:
                assert [m for m in pos if 0 < pos[m] < car]
        group = [step["m"], *step.get("carry", [])]
        if step["from"]:
            # The mover and those on its head; a solo leaves its riders where they were.
            assert all(m in stacks[step["from"]] for m in group)
            stacks[step["from"]] = [m for m in stacks[step["from"]] if m not in group]
            if not stacks[step["from"]]:
                del stacks[step["from"]]
        q = step.get("end", step["to"])
        if q:
            stacks.setdefault(q, []).extend(group)
        if step.get("square") == "flip":
            stacks[q].reverse()
        if "stack" in step:
            assert sorted(step["stack"]) == sorted(stacks[q])
            stacks[q] = list(step["stack"])
        for m in group:
            pos[m] = q
        if car is None and out.get("enter") == i:
            assert max(pos.values()) > track // 2
            car = track
    assert not drives
    return sorted(pos, key=lambda m: (pos[m], stacks[pos[m]].index(m) if pos[m] else -lane[m]), reverse=True)


# ---------------------------------------------------------------- the rules
def test_the_rules_are_copied_into_the_setup_and_draw_nothing():
    r = rules(track=22, shuffle=True)
    assert race.deal_rules(r, {"map": r.maps[0]}) == {"shuffle": True, "alpaca": {"at": 11, "dice": list(DICE)}}
    assert race.deal_rules(rules(alpaca=False), {"map": r.maps[0]}) == {}
    assert race.deal_rules(race.Rules.of({k: v for k, v in CFG.items() if k not in ("shuffle", "alpaca")}, MEMBERS),
                           {"map": r.maps[0]}) == {}
    # The deal draws the same squares and skills with or without them.
    on = race.Rules.of({**CFG, "shuffle": True, "alpaca": {"dice": list(DICE)}}, MEMBERS)
    off = race.Rules.of({k: v for k, v in CFG.items() if k not in ("shuffle", "alpaca")}, MEMBERS)
    for k in range(20):
        a, b = random.Random(k), random.Random(k)
        dealt = {**race.deal(on, a), **race.deal_skills(on, a)}
        race.deal_rules(on, dealt)
        assert dealt == {**race.deal(off, b), **race.deal_skills(off, b)} and a.random() == b.random()


@pytest.mark.parametrize("bad", [{"dice": []}, {"dice": [0, 1, 2]}, {}])
def test_an_alpaca_without_a_die_is_refused(bad):
    with pytest.raises(ValueError):
        race.Rules.of({**CFG, "alpaca": bad}, MEMBERS)
    assert race.Rules.of({**CFG, "alpaca": None}, MEMBERS).alpaca == rules(alpaca=False).alpaca == ()


def test_a_setup_without_them_runs_as_before():
    r = race.Rules.of({**CFG, "shuffle": True, "alpaca": {"dice": list(DICE)}}, MEMBERS)
    dealer = random.Random(4)
    for k in range(50):
        su = {**race.deal(r, dealer), **race.deal_skills(r, dealer)}
        assert set(race.run(r, su, race.SimRng(k))) == {"ranking", "start", "order", "rolls", "moves", "rest"}


# One race on 20 squares, the middle on 10, every member rolling 1 to 6; the order is the manifest's.
ROUND0 = [die(6), die(6), die(3), die(2), die(1)]   # J 6, N 6 on J, B 3, X 2, S 1
ROUND1 = [die(5), die(1), die(6), die(6), die(6)]   # J carries N past the middle: the alpaca comes out
ROUND2 = [die(1)] * 5 + [die(6)]                     # its first turn: 6 back towards the start, to 14, nobody there
ROUND3 = [die(1), die(1), die(2), die(2), die(2)]   # J and N step onto 14, the alpaca's square
# A round's dice for its order (shuffle), by those taking turns in member order: 6 5 4 3 2 keeps the members' order,
# 1 after them puts the alpaca last, and 5 4 3 2 1 for the members with 6 for the alpaca puts it first.
KEEP_ORDER = FIRST
ALPACA_LAST = FIRST + [die(1)]
ALPACA_FIRST = [die(5), die(4), die(3), die(2), die(1), die(6)]


def test_the_alpaca_comes_out_past_the_middle_and_carries_those_it_reaches():
    rolls = ROUND0 + ROUND1 + ROUND2 + ROUND3 + [die(3)] + [die(1), die(1), die(1), die(5), die(2), die(4)] + \
        [die(6), die(6), die(1), die(1), die(1), die(4)]
    r = rules()
    out = race.run(r, setup(r), Script(OPEN + rolls))
    # Out after the first move that takes a dumpling past square 10; it waits on the finish and takes turns from the
    # next round on, last in the order the whole race keeps.
    assert out["enter"] == 5 and out["moves"][5] == {"m": J, "dice": [5], "steps": 5, "from": 6, "to": 11,
                                                     "carry": [N]}
    assert out["orders"] == [[J, N, B, X, S]] * 2 + [[J, N, B, X, S, A]] * 4 and "orderRolls" not in out
    d = out["drives"]
    # Round 2: 6 from the finish, to 14; nobody on 14 to 20.
    assert d[0] == {"r": 2, "at": 15, "face": 6, "from": 20, "to": 14}
    # Round 3: J and N stepped onto 14 and ride; 3 squares to 11 takes X on 11, B on 12 and them, further along on
    # top. sinuo on 10 is still ahead.
    assert out["moves"][15:17] == [{"m": J, "dice": [1], "steps": 1, "from": 13, "to": 14},
                                   {"m": N, "dice": [1], "steps": 1, "from": 13, "to": 14}]
    assert d[1] == {"r": 3, "at": 20, "face": 3, "from": 14, "to": 11, "take": [X, B, J, N]}
    # Round 4: the riders are not held. J moves on with N on its head, then B; X walks off alone; sinuo passes the
    # alpaca, which does nothing.
    assert out["moves"][20] == {"m": J, "dice": [1], "steps": 1, "from": 11, "to": 12, "carry": [N]}
    assert out["moves"][22] == {"m": B, "dice": [1], "steps": 1, "from": 11, "to": 12}
    assert out["moves"][23] == {"m": X, "dice": [5], "steps": 5, "from": 11, "to": 16}
    assert out["moves"][24] == {"m": S, "dice": [2], "steps": 2, "from": 10, "to": 12}
    # Nobody short of 11 now: it goes back to the finish first, then drives 4 to 16 and picks up X there.
    assert d[2] == {"r": 4, "at": 25, "face": 4, "back": 11, "from": 20, "to": 16, "take": [X]}
    # Round 5: sinuo reaches the finish; the alpaca's die after it is only shown.
    assert out["moves"][-1] == {"m": S, "dice": [1], "steps": 1, "from": 19, "to": 20}
    assert len(d) == 3 and out["rest"] == [{"m": A, "face": 4}]
    assert out["ranking"] == [S, B, N, J, X] == replay(out, 20)
    # Every member still moves once a round.
    assert len(out["moves"]) == 30


def test_with_nobody_left_ahead_the_alpaca_goes_home_and_leaves_its_riders():
    rolls = ROUND0 + ROUND1 + ROUND2 + ROUND3 + [die(6)]
    r = rules()
    out = race.run(r, setup(r), Script(OPEN + rolls))
    d = out["drives"]
    # 6 from 14 takes everyone on 8 to 14, sinuo on 10 at the bottom; with nobody short of 8 it goes home.
    assert d[1] == {"r": 3, "at": 20, "face": 6, "from": 14, "to": 8, "take": [S, X, B, J, N], "home": True}
    assert d[2]["from"] == 20 and "back" not in d[2]
    # They leave the square in turn: J first, with N on its head.
    assert out["moves"][20]["from"] == 8 and out["moves"][20]["carry"] == [N]
    assert out["ranking"] == replay(out, 20)


def test_the_alpaca_stops_short_of_the_start_and_never_takes_the_start_line():
    # 14 squares, the middle on 7, a trip square on 4 that sets a group back to 1. Every round keeps the members'
    # order; the alpaca rolls the lowest until round 4, where it rolls the highest.
    r = rules(track=14, squares=[{"at": 4, "kind": "trip", "by": 3}], shuffle=True)
    belows = (OPEN + [die(6), die(2), die(2), die(3), die(3)] + KEEP_ORDER + [die(2)] + [die(1)] * 4
              + ALPACA_LAST + [die(1)] * 5 + [die(6)] + ALPACA_LAST + [die(1)] * 5 + [die(6)] + ALPACA_FIRST + [die(3)])
    out = race.run(r, setup(r), Script(belows))
    assert out["enter"] == 5 and out["orders"][4][0] == A
    assert out["orderRolls"][4] == [[{"m": m, "face": f} for m, f in zip((J, N, B, X, S, A), (5, 4, 3, 2, 1, 6))]]
    # nailin is back on 1, the rest on 2: 3 from square 2 stops on 1 and takes them all; nobody is left ahead.
    assert out["drives"][2] == {"r": 4, "at": 20, "face": 3, "from": 2, "to": 1, "take": [N, B, X, S], "home": True}
    assert out["ranking"] == replay(out, 14)
    for k in range(400):
        out = race.run(r, setup(r), race.SimRng(k))
        for d in out.get("drives", []):
            assert 1 <= d["to"] < d["from"] <= 14 and d["to"] == max(1, d["from"] - d["face"])
        assert out["ranking"] == replay(out, 14)


def test_each_round_from_the_second_rolls_for_its_order_as_the_opening_does_the_alpaca_too():
    r = rules(shuffle=True)
    # Round 1 rolls 6 5 4 3 2: the order stays; in round 2 the alpaca rolls 6 and goes first, the members after it as
    # they rolled.
    belows = OPEN + ROUND0 + KEEP_ORDER + ROUND1 + ALPACA_FIRST + [die(6)] + [die(1)] * 5
    out = race.run(r, setup(r), Script(belows))
    assert out["orders"][:3] == [[J, N, B, X, S], [J, N, B, X, S], [A, J, N, B, X, S]]
    assert out["orderRolls"][0] == [] and len(out["orderRolls"]) == len(out["orders"])
    assert out["orderRolls"][2] == [[{"m": m, "face": f} for m, f in zip((J, N, B, X, S, A), (5, 4, 3, 2, 1, 6))]]
    assert out["drives"][0] == {"r": 2, "at": 10, "face": 6, "from": 20, "to": 14}
    assert [m["m"] for m in out["moves"][10:15]] == [J, N, B, X, S]
    # Those on the same face roll again, all in the same round, each compared within its own tie: 6 6 3 3 1, then
    # 2 5 4 4 for the sixes and the threes, then 1 6 for the threes still tied: N J X B S.
    plain = rules(shuffle=True, alpaca=False)
    out = race.run(plain, setup(plain), Script(OPEN + ROUND0 + [die(6), die(6), die(3), die(3), die(1)]
                                               + [die(2), die(5), die(4), die(4)] + [die(1), die(6)]))
    assert out["orders"][1] == [N, J, X, B, S] and [m["m"] for m in out["moves"][5:10]] == [N, J, X, B, S]
    faces = [[(x["m"], x["face"]) for x in got] for got in out["orderRolls"][1]]
    assert faces == [[(J, 6), (N, 6), (B, 3), (X, 3), (S, 1)], [(J, 2), (N, 5), (B, 4), (X, 4)], [(B, 1), (X, 6)]]
    assert "drives" not in out and "enter" not in out


def test_the_order_dice_part_ties_as_they_always_did():
    # opening() looks for ties among those who just rolled only; the reference compares everyone with everyone.
    def reference(n, below):
        keys, rounds, rolling = [[] for _ in range(n)], [], list(range(n))
        while rolling:
            got = [(d, below(race.ORDER_FACES) + 1) for d in rolling]
            for d, face in got:
                keys[d].append(face)
            rounds.append(got)
            rolling = [d for d in range(n) if any(e != d and keys[e] == keys[d] for e in range(n))]
        return sorted(range(n), key=lambda d: keys[d], reverse=True), rounds

    for k in range(3000):
        n = 5 + k % 2
        a, b = random.Random(k), random.Random(k)
        assert race.opening(n, lambda m: a.randrange(m)) == reference(n, lambda m: b.randrange(m))
        assert a.random() == b.random()


def test_simulated_races_draw_the_same_without_keeping_the_order_dice():
    r = race.Rules.of({**CFG, "shuffle": True, "alpaca": {"dice": list(DICE)}}, MEMBERS)
    dealer = random.Random(5)
    for k in range(30):
        su = {**race.deal(r, dealer), **race.deal_skills(r, dealer)}
        su.update(race.deal_rules(r, su))
        kept = race.run(r, su, race.SimRng(k))
        assert race.run(r, su, race.SimRng(k), keep_dice=False) == {x: v for x, v in kept.items() if x != "orderRolls"}


def test_the_draws_come_in_the_order_run_tells():
    # Recomputed from the stream: the lanes, the order's dice, then round by round the dice for its order (from the
    # second round on, by those taking turns in member order, the alpaca after them), every die in the round's order,
    # then rest's dice.
    r = rules(track=30, shuffle=True)
    everyone = MEMBERS + (A,)

    def tied(keys):
        return [m for m in keys if any(e != m and keys[e] == keys[m] for e in keys)]

    for k in range(200):
        seed = k.to_bytes(32, "big")
        out = race.run_seed(r, setup(r), seed)
        rng = race.StreamRng(seed)
        for i in range(4, 0, -1):
            rng.below(i + 1)
        for got in out["rolls"]:
            for _ in got:
                rng.below(6)
        moves, drives, rest = iter(out["moves"]), iter(out.get("drives", [])), iter(out["rest"])
        ended = False
        for n, order in enumerate(out["orders"]):
            thrown = out["orderRolls"][n]
            if n:
                # As the opening: everyone, then those still on the same faces as another, until all differ; the
                # order is their faces high to low.
                keys = {m: [] for m in sorted(order, key=everyone.index)}
                for got in thrown:
                    assert [x["m"] for x in got] == tied(keys)
                    for x in got:
                        assert DICE[rng.below(6)] == x["face"]
                        keys[x["m"]].append(x["face"])
                assert not tied(keys) and order == sorted(keys, key=lambda m: keys[m], reverse=True)
            else:
                assert thrown == [] and order == out["order"]
            for m in order:
                face = DICE[rng.below(6)]
                if ended:
                    assert next(rest) == {"m": m, "face": face}
                elif m == A:
                    turn = next(drives)
                    assert turn["face"] == face and turn["r"] == n
                else:
                    step = next(moves)
                    assert step["m"] == m and step["dice"] == [face]
                    ended = step is out["moves"][-1]
        assert next(moves, None) is None and next(drives, None) is None and next(rest, None) is None
        assert (len(out["moves"]) + len([x for x in out["rest"] if x["m"] != A])) % 5 == 0


def test_the_moves_and_drives_alone_rebuild_every_race_on_the_manifests_maps():
    r = race.Rules.of({**CFG, "shuffle": True, "alpaca": {"dice": list(DICE)}}, MEMBERS)
    dealer = random.Random(12)
    took = homes = backs = on_square = climbing = 0
    for i in range(400):
        su = {**race.deal(r, dealer), **race.deal_skills(r, dealer)}
        su.update(race.deal_rules(r, su))
        out = race.run(r, su, race.SimRng(i))
        assert out["ranking"] == replay(out, su["map"]["track"])
        assert -(-len(out["moves"]) // 5) == len(out["orders"])
        assert all(len(o) == (6 if A in o else 5) for o in out["orders"])
        # Squares and skills do nothing to a drive or to what it carries: the replay above applies neither, so a drive
        # that stops on a special square with riders, or carries a climber below the top, would have shown.
        squares = {q["at"] for q in su["map"]["squares"]} | {q["to"] for q in su["map"]["squares"] if "to" in q}
        climbers = {m for m, k in su["skills"].items() if k["id"] == "climb"}
        for d in out.get("drives", []):
            took += bool(d.get("take"))
            homes += bool(d.get("home"))
            backs += "back" in d
            on_square += bool(d.get("take")) and d["to"] in squares
            climbing += any(m in climbers for m in d.get("take", [])[:-1])
    assert took and homes and backs and on_square and climbing


# ---------------------------------------------------------------- the schedule
def make():
    m = Manifest.load()
    cfg = m.park["race"]
    cfg.update(sims=200, shuffle=True, alpaca={"dice": list(DICE)})
    clock = Clock(T0 + 1)
    g = Game(Store(":memory:"), m, now=clock)
    races = Races(lambda: g, Park(lambda: g), dealer=random.Random(3), seeds=seeds())
    g.status(TOKEN)
    return races, clock


def started(k=0):
    races, clock = make()
    clock.t = T0 + k * CFG["interval"]
    races.tick()
    clock.t += CFG["betting"] + 1
    races.tick()
    return races, clock


@pytest.mark.parametrize("setup_, version, plays", [
    ({"shuffle": True}, "1.3.0", True), ({"alpaca": {"at": 9}}, "1.3.0-rc.1", True), ({"shuffle": True}, "1.2.6", False),
    ({"map": {}, "alpaca": {"at": 9}}, "1.2.5", False), ({"map": {"id": "t"}}, "1.2.5", True),
    ({"map": {"id": "t"}}, "1.2.4", False), ({"boost": 3, "trip": 5}, None, True), ({"shuffle": True}, None, False),
])
def test_a_race_by_the_new_rules_needs_1_3_0(setup_, version, plays):
    assert park_race.plays(setup_, version) is plays


def test_a_race_is_prepared_with_the_rules_in_its_setup():
    races, clock = make()
    races.tick()
    su = races.view(TOKEN, "1.3.0")["race"]["setup"]
    assert su["shuffle"] is True and su["alpaca"] == {"at": su["map"]["track"] // 2, "dice": list(DICE)}
    assert {"map", "skills", "dice", "chance"} < set(su)


@pytest.mark.parametrize("version, plays", [("1.3.0", True), ("1.3.0-rc.1", True), ("1.2.6", False),
                                             ("1.2.5", False), (None, False)])
def test_a_client_from_before_1_3_0_gets_the_result_without_the_moves(version, plays):
    races, clock = started()
    r = races.view(TOKEN, version)["race"]
    assert r["phase"] == "running" and r["replay"] is plays and ("moves" in r) is plays and len(r["ranking"]) == 5
    assert ("orders" in r) is plays and ("drivesMs" in r) is plays
    clock.t = r["endsAt"] + 1
    races.tick()
    past = races.history(TOKEN, version)["races"][0]
    assert past["replay"] is plays
    if plays:
        assert races.replay(TOKEN, past["id"], version)["race"]["drives"] == r["drives"]
    else:
        with pytest.raises(Exception) as e:
            races.replay(TOKEN, past["id"], version)
        assert e.value.code == "no_replay"


def test_a_race_by_the_new_rules_lasts_as_long_as_its_changes_of_order_and_drives_take():
    seen = 0
    for k in range(6):
        races, clock = started(k)
        r = races.view(TOKEN, "1.3.0")["race"]
        rounds = -(-len(r["moves"]) // park_race.ROUND)
        assert len(r["orders"]) == rounds and r["shuffleMs"] == park_race.SHUFFLE_MS
        assert r["orderRollMs"] == park_race.ORDER_ROLL_MS == park_race.REROLL_MS
        assert len(r["orderRolls"]) == rounds and r["orderRolls"][0] == [] and all(r["orderRolls"][1:])
        assert r["drivePace"] == park_race.DRIVE and len(r["drivesMs"]) == len(r["drives"])
        last = r["slowFrom"] // park_race.ROUND
        for turn, ms in zip(r["drives"], r["drivesMs"]):
            want = park_race.drive_ms(turn, park_race.DRIVE)
            assert ms == (want if turn["r"] < last else want * park_race.SLOW_MS // park_race.STEP_MS)
        assert ("enter" in r) is ("enterMs" in r)
        if "enter" in r:
            seen += 1
            assert r["enterMs"] == park_race.ENTER_MS
            assert all(turn["r"] > r["enter"] // park_race.ROUND for turn in r["drives"])
        assert r["endsAt"] == r["startsAt"] + (
            r["leadMs"] + rounds * r["rollMs"] + sum(r["stepsMs"]) + len(r.get("cuts", [])) * r.get("cutMs", 0)
            + sum(map(len, r["orderRolls"])) * r["orderRollMs"] + (rounds - 1) * r["shuffleMs"] + sum(r["drivesMs"])
            + r.get("enterMs", 0) + park_race.TAIL_MS) / 1000
        assert r["ranking"] == replay(r, r["setup"]["map"]["track"])
    assert seen


def test_a_drive_takes_as_long_as_what_it_shows():
    pace = park_race.DRIVE
    plain = {"r": 3, "at": 20, "face": 3, "from": 14, "to": 11}
    assert park_race.drive_ms(plain, pace) == pace["lit"] + 3 * pace["sq"] + pace["rest"]
    full = {**plain, "back": 9, "take": [J], "home": True}
    assert park_race.drive_ms(full, pace) == park_race.drive_ms(plain, pace) + 2 * pace["away"] + pace["take"]
    # Scaled down with the rest when the race is too long for its window.
    moves = [{"m": "a", "steps": 3, "to": 3}] * 12
    drives = [plain, full]
    whole = park_race.paced_times(moves, drives=drives, enter=4, shuffle=True)
    half = park_race.paced_times(moves, 0.5, drives=drives, enter=4, shuffle=True)
    assert half["drive"] == {k: v // 2 for k, v in pace.items()}
    assert half["shuffle"] == whole["shuffle"] // 2 and half["enter"] == whole["enter"] // 2
    assert half["orderRoll"] == whole["orderRoll"] // 2 == park_race.ORDER_ROLL_MS // 2
    assert park_race.paced_ms(half, 2, 5) <= park_race.paced_ms(whole, 2, 5) // 2
    assert park_race.paced_ms(whole, 2, 5) == park_race.paced_ms(whole, 2) + 5 * park_race.ORDER_ROLL_MS
    # Without the rules nothing is added.
    assert set(park_race.paced_times(moves)) == {"pace", "steps", "roll", "cut"}


def test_the_client_fixture_is_what_the_rules_give():
    races = gen_race_alpaca_fixture.build()
    assert json.loads(gen_race_alpaca_fixture.FIXTURE.read_text(encoding="utf-8")) == races
    seen = set()
    for r in races:
        assert r["ranking"] == replay(r, r["setup"]["map"]["track"])
        times = {"steps": r["stepsMs"], "roll": r["rollMs"], "cut": r.get("cutMs", 0), "shuffle": r["shuffleMs"],
                 "orderRoll": r["orderRollMs"], "drives": r["drivesMs"], "enter": r.get("enterMs", 0)}
        length = (r["leadMs"] + park_race.paced_ms(times, len(r.get("cuts", [])), park_race.order_rolls_of(r))
                  + park_race.TAIL_MS)
        assert r["endsAt"] == r["startsAt"] + length / 1000
        if any(len(dice) > 1 for dice in r["orderRolls"]):
            seen.add("reroll")
        seen.update(k for d in r["drives"] for k in ("back", "take", "home") if k in d)
        ats = [d["at"] for d in r["drives"]]
        if len(ats) > len(set(ats)):
            seen.add("shared")
        if any(o[0] == A for o in r["orders"]):
            seen.add("first")
        if any(d["r"] >= r["slowFrom"] // park_race.ROUND for d in r["drives"]):
            seen.add("slow")
    # Between them the races show what the client has to play: see gen_race_alpaca_fixture.CASES.
    assert seen == {"back", "take", "home", "shared", "first", "slow", "reroll"}
